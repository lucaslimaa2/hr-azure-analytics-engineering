# Data contract

The agreement between the **source** (generated in-pipeline), the **raw** zone, and
the **curated** zone. These cleaning rules are **engine-agnostic**, they describe the
raw → curated mapping regardless of *how* it's implemented.

**Implemented by:** the **Transform** step, now written in **Synapse serverless SQL**
(`OPENROWSET` the raw JSON → clean in T-SQL → `CETAS` to curated parquet); see
`synapse/sql/`. *(Originally drafted as a pandas function; this doc was the spec it
implemented, and remains the spec for the SQL version.)*

Data is **synthetic only** and **generated in-pipeline**, no external API. The
**Generate step** (`functions/shared/generate.py`, run via GitHub Actions as
`scripts/run_generate.py`) produces each month's **full-roster snapshot**
deterministically and writes it to raw.

---

## 1. Raw schema (as authored / as-received)

One JSON object per employee. **The feed is a monthly full-roster snapshot
("periodic snapshot"):** each monthly run writes the **entire current headcount**
as one file `raw/{yyyy}/{MM}/employees.json`. The first month seeds the existing
workforce (~1,000); each later month = the **prior month's survivors minus
terminations, plus ~200 new hires**. The **same `employee_id` recurs across months**
(a person who stays appears in every month until they leave), so a month is a complete
picture of who was employed *that month*, not a delta. Departures are modeled by
**absence**: a terminated employee simply stops appearing the next month, so every row
in a snapshot has `employment_status` = `Active`. Field *values* are deliberately messy
(see §2); field *names* are stable.

There is **no per-row date field**, which month a snapshot represents comes from the
**partition folder** (`raw/2026/03/…` → March 2026), not from inside the records.

| field | intended meaning | clean example |
|---|---|---|
| `employee_id` | source-system employee id (our key) | `1` |
| `first_name` | given name | `"Ana"` |
| `last_name` | family name | `"Silva"` |
| `email` | corporate email | `"ana.silva@corp.com.br"` |
| `gender` | gender | `"female"` |
| `birth_date` | date of birth | `"1990-04-12"` |
| `hire_date` | hire date | `"2019-03-01"` |
| `department` | org department | `"Engineering"` |
| `job_title` | role title | `"Senior Analyst"` |
| `employment_type` | contract type | `"Full-time"` |
| `employment_status` | current status | `"Active"` |
| `salary` | monthly gross | `8500.00` |
| `currency` | salary currency | `"BRL"` |
| `manager_id` | manager's `id` (nullable) | `5` |
| `location` | office city | `"São Paulo"` |
| `created_at` | record creation ts | `"2026-06-04T13:46:59.545Z"` |

Raw is stored **immutable and as-received** in `raw/{yyyy}/{MM}/`. No parsing,
no cleaning, never overwritten.

---

## 2. Messiness catalog (injected on purpose)

| field(s) | injected defect | cleaning the transform applies |
|---|---|---|
| `first_name`, `last_name`, `job_title` | leading/trailing whitespace, double spaces | trim + collapse internal whitespace |
| `department` | mixed casing & abbreviations: `engineering` / `ENG` / `" Eng "` | map to canonical set |
| `gender` | `female` / `Female` / `F` / `f` / `""` | normalize → `female` / `male` / `other` / `unknown` |
| `employment_status` | always `Active`, in mixed casing/abbrev: `Active` / `active` / `ACTIVE` / `A` | normalize → `Active`; `On Leave` / `Terminated` / `Unknown` handled defensively (never produced by the generator) |
| `employment_type` | `Full-time` / `Full Time` / `FT` | normalize → `Full-time` / `Part-time` / `Contractor` / `Intern` / `Unknown` |
| `hire_date`, `birth_date` | mixed formats: ISO, `MM/DD/YYYY`, `DD-MM-YYYY`, epoch int, `""`, `"N/A"` | parse → ISO date; unparseable → null |
| `salary` | number vs string: `8500`, `"R$ 8.500,00"`, `"8,500.00"`, negative, `0`, blank | strip currency/separators → float; ≤0 or blank → null |
| `email` | UPPERCASE, trailing spaces, missing, malformed (no `@`) | lowercase + trim; invalid/missing → null |
| `manager_id` | `5`, `"5"`, `0`, `""`, `null` | coerce to nullable int; `0`/blank → null |
| `employee_id` | string vs int; **duplicate employee rows** (conflicting values) | coerce to int; dedupe **within a month** on `(snapshot_year, snapshot_month, employee_id)`, keep last |
| `location` | inconsistent spellings, `""`, `"N/A"`, `"-"` | trim; null tokens → null |
| (any field) | null tokens `""`, `"null"`, `"N/A"`, `"-"` | treated as missing |

> **Note on messiness stability:** the whole roster is replayed deterministically
> from the start month, seeded by `(seed, month)`, so each monthly snapshot is fully
> reproducible (a re-run of `Generate` for a given month produces byte-identical raw,
> which is what lets raw stay immutable). Because it's a replay, the same person keeps
> the same id and the same messy style every month they appear.

---

## 3. Curated schema (typed, cleaned, modeled → parquet)

One row per employee **per month**, written to `curated/{yyyy}/{MM}/` as parquet by
`CETAS`. Each month's snapshot is transformed independently (clean the month's roster,
dedupe within the month on `employee_id` keeping the last). The same employee appears
once in every month they were employed.

| column | type | derivation |
|---|---|---|
| `snapshot_year` | int64 | from the **partition folder** `raw/{yyyy}/…` (partition key) |
| `snapshot_month` | int64 | from the **partition folder** `raw/…/{MM}/…` (partition key) |
| `reference_date` | date | first of the snapshot month `DATEFROMPARTS(snapshot_year, snapshot_month, 1)` (the month this picture represents) |
| `employee_id` | int64 | from `employee_id` |
| `first_name` | string | trimmed |
| `last_name` | string | trimmed |
| `full_name` | string | `first_name + " " + last_name` |
| `email` | string (nullable) | lowercased/trimmed; null if invalid |
| `gender` | string | normalized closed set |
| `birth_date` | date (nullable) | parsed |
| `age` | int (nullable) | whole years, `birth_date` → snapshot month-end |
| `hire_date` | date (nullable) | parsed |
| `tenure_months` | int (nullable) | whole months, `hire_date` → snapshot month-end |
| `department` | string | canonical |
| `job_title` | string | trimmed |
| `employment_type` | string | normalized closed set |
| `employment_status` | string | normalized closed set |
| `salary` | float64 (nullable) | cleaned; ≤0 → null |
| `currency` | string | normalized; default `BRL` |
| `manager_id` | int64 (nullable) | coerced |
| `location` | string (nullable) | cleaned |
| `ingested_at` | timestamp | from `created_at` |

**Canonical sets**

- `department`: Engineering · Sales · Human Resources · Finance · Marketing · Operations · Customer Support · Product
- `employment_type`: Full-time · Part-time · Contractor · Intern · Unknown
- `employment_status`: Active · On Leave · Terminated · Unknown *(only `Active` occurs in this dataset; the others are defensive)*
- `gender`: female · male · other · unknown
