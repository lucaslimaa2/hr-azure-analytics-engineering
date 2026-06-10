"""Deterministic MONTHLY full-roster HR snapshot generator (the pipeline's source).

Each month is a FULL snapshot of the workforce: the previous month's survivors,
minus that month's terminations, plus that month's new hires. So the same
employee recurs every month they're employed (a "periodic snapshot"), and
headcount evolves — e.g. 1000, then +hires / -leavers each month.

Stateless & deterministic: ``generate_month(year, month)`` REPLAYS from the start
month to the target (cheap), so any month is reproducible with no stored state —
which is what lets the raw zone stay immutable.

All data is synthetic and deliberately messy (see docs/DATA_CONTRACT.md).
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from random import Random

# --------------------------------------------------------------------------- #
# Canonical value pools (Brazilian flavour — fits the Brazil South / LGPD theme)
# --------------------------------------------------------------------------- #

FIRST_NAMES = [
    "Ana",
    "Bruno",
    "Carla",
    "Diego",
    "Eduarda",
    "Felipe",
    "Gabriela",
    "Henrique",
    "Isabela",
    "João",
    "Larissa",
    "Marcos",
    "Natália",
    "Otávio",
    "Patrícia",
    "Rafael",
    "Sofia",
    "Thiago",
    "Vanessa",
    "William",
    "Beatriz",
    "Caio",
    "Daniela",
    "Eduardo",
    "Fernanda",
    "Gustavo",
    "Helena",
    "Igor",
    "Júlia",
    "Lucas",
]
LAST_NAMES = [
    "Silva",
    "Santos",
    "Oliveira",
    "Souza",
    "Lima",
    "Pereira",
    "Costa",
    "Almeida",
    "Ferreira",
    "Rodrigues",
    "Gomes",
    "Martins",
    "Araújo",
    "Ribeiro",
    "Carvalho",
    "Barbosa",
    "Rocha",
    "Dias",
    "Nascimento",
    "Moreira",
    "Cardoso",
    "Teixeira",
]
CITIES = [
    "São Paulo",
    "Rio de Janeiro",
    "Belo Horizonte",
    "Curitiba",
    "Porto Alegre",
    "Recife",
    "Salvador",
    "Brasília",
    "Fortaleza",
    "Campinas",
    "Florianópolis",
]
DEPARTMENTS = [
    "Engineering",
    "Sales",
    "Human Resources",
    "Finance",
    "Marketing",
    "Operations",
    "Customer Support",
    "Product",
]
DEPT_TITLES = {
    "Engineering": ["Junior Engineer", "Engineer", "Senior Engineer", "Lead Engineer", "Engineering Manager"],
    "Sales": ["Sales Rep", "Account Executive", "Senior Account Executive", "Sales Lead", "Sales Manager"],
    "Human Resources": ["HR Assistant", "HR Analyst", "Senior HR Analyst", "HR Lead", "HR Manager"],
    "Finance": [
        "Finance Assistant",
        "Financial Analyst",
        "Senior Financial Analyst",
        "Finance Lead",
        "Finance Manager",
    ],
    "Marketing": [
        "Marketing Assistant",
        "Marketing Analyst",
        "Senior Marketing Analyst",
        "Marketing Lead",
        "Marketing Manager",
    ],
    "Operations": [
        "Operations Assistant",
        "Operations Analyst",
        "Senior Operations Analyst",
        "Operations Lead",
        "Operations Manager",
    ],
    "Customer Support": [
        "Support Agent",
        "Senior Support Agent",
        "Support Specialist",
        "Support Lead",
        "Support Manager",
    ],
    "Product": [
        "Associate PM",
        "Product Manager",
        "Senior Product Manager",
        "Group PM",
        "Director of Product",
    ],
}
EMPLOYMENT_TYPES = ["Full-time", "Part-time", "Contractor", "Intern"]
GENDERS = ["female", "male", "other"]
SALARY_BANDS = [(3000, 6000), (5000, 9000), (8000, 14000), (12000, 22000), (18000, 35000)]


@dataclass(frozen=True)
class GenConfig:
    """Generation parameters. Same config + month → same snapshot."""

    start_date: date = date(2026, 1, 1)  # the first monthly snapshot
    seed: int = 42
    start_count: int = 1000  # workforce size in the first month
    hires_per_month: int = 200  # new hires added each later month
    term_rate: float = 0.04  # fraction of the roster that leaves each month


# --------------------------------------------------------------------------- #
# Month helpers
# --------------------------------------------------------------------------- #


def _next_month(d: date) -> date:
    return date(d.year + (d.month // 12), (d.month % 12) + 1, 1)


def _month_end(d: date) -> date:
    return _next_month(d) - timedelta(days=1)


# --------------------------------------------------------------------------- #
# Clean record construction
# --------------------------------------------------------------------------- #


def _strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def _email(first: str, last: str, emp_id: int) -> str:
    local = f"{_strip_accents(first)}.{_strip_accents(last)}".lower().replace(" ", "")
    return f"{local}{emp_id}@corp.com.br"


def _rand_date(rng: Random, start: date, end: date) -> date:
    return start + timedelta(days=rng.randint(0, max((end - start).days, 0)))


def _new_employee(emp_id: int, rng: Random, *, historical: bool, period: date, cfg: GenConfig) -> dict:
    """Build one clean employee. ``historical`` = part of the seeded starting
    workforce (hired in the past); otherwise hired during ``period``."""
    ref_year = period.year
    first = rng.choice(FIRST_NAMES)
    last = rng.choice(LAST_NAMES)
    age = rng.randint(22, 60)
    birth = _rand_date(rng, date(ref_year - age, 1, 1), date(ref_year - age, 12, 28))
    if historical:
        earliest = max(date(ref_year - 15, 1, 1), date(birth.year + 18, 1, 1))
        hire = _rand_date(rng, earliest, period)
    else:
        hire = _rand_date(rng, period, _month_end(period))  # hired this month
    dept = rng.choice(DEPARTMENTS)
    rung = rng.choices(range(5), weights=[35, 30, 20, 10, 5])[0]
    low, high = SALARY_BANDS[rung]
    created = datetime(hire.year, hire.month, hire.day, rng.randint(8, 18), rng.randint(0, 59), tzinfo=UTC)
    # manager: a random earlier-id employee (or none for ~5%, e.g. execs)
    manager_id = None if (emp_id == 1 or rng.random() < 0.05) else rng.randint(1, emp_id - 1)
    return {
        "employee_id": emp_id,
        "first_name": first,
        "last_name": last,
        "email": _email(first, last, emp_id),
        "gender": rng.choices(GENDERS, weights=[48, 48, 4])[0],
        "birth_date": birth.isoformat(),
        "hire_date": hire.isoformat(),
        "department": dept,
        "job_title": DEPT_TITLES[dept][rung],
        "employment_type": rng.choices(EMPLOYMENT_TYPES, weights=[80, 8, 8, 4])[0],
        "employment_status": "Active",
        "salary": round(rng.uniform(low, high), 2),
        "currency": "BRL",
        "manager_id": manager_id,
        "location": rng.choice(CITIES),
        "created_at": created.isoformat().replace("+00:00", "Z"),
        "_dirt_seed": (cfg.seed * 1_000_003 + emp_id) & 0xFFFFFFFF,
    }


# --------------------------------------------------------------------------- #
# Roster evolution (carry forward → terminate → hire), replayed deterministically
# --------------------------------------------------------------------------- #


def _build_initial(cfg: GenConfig) -> tuple[list[dict], int]:
    rng = Random(f"{cfg.seed}:init")
    roster = [
        _new_employee(i, rng, historical=True, period=cfg.start_date, cfg=cfg)
        for i in range(1, cfg.start_count + 1)
    ]
    return roster, cfg.start_count + 1


def _month_step(roster: list[dict], period: date, cfg: GenConfig, next_id: int) -> tuple[list[dict], int]:
    """One month of churn: drop ~term_rate of the roster, then add hires_per_month."""
    rng = Random(f"{cfg.seed}:{period.isoformat()}")
    survivors = [e for e in roster if rng.random() >= cfg.term_rate]
    for _ in range(cfg.hires_per_month):
        survivors.append(_new_employee(next_id, rng, historical=False, period=period, cfg=cfg))
        next_id += 1
    return survivors, next_id


def _roster_for(target: date, cfg: GenConfig) -> list[dict]:
    """Replay from start_date to ``target`` and return that month's full roster."""
    roster, next_id = _build_initial(cfg)
    period = cfg.start_date
    while period < target:
        period = _next_month(period)
        roster, next_id = _month_step(roster, period, cfg, next_id)
    return roster


# --------------------------------------------------------------------------- #
# Messy serialization — stable per employee, driven by _dirt_seed
# --------------------------------------------------------------------------- #


def _pad(value: str, rng: Random) -> str:
    style = rng.choices(["none", "trail", "lead", "double"], weights=[80, 7, 7, 6])[0]
    if style == "trail":
        return value + "  "
    if style == "lead":
        return "  " + value
    if style == "double":
        return value.replace(" ", "  ", 1) if " " in value else value + " "
    return value


def _br_money(n: float) -> str:
    s = f"{n:,.2f}"
    return "R$ " + s.replace(",", "X").replace(".", ",").replace("X", ".")


def _messy_date(iso: str, style: str) -> object:
    d = date.fromisoformat(iso)
    if style == "iso":
        return iso
    if style == "us":
        return d.strftime("%m/%d/%Y")
    if style == "dmy":
        return d.strftime("%d-%m-%Y")
    if style == "epoch":
        return int(datetime(d.year, d.month, d.day, tzinfo=UTC).timestamp())
    if style == "na":
        return "N/A"
    return ""


def serialize_messy(emp: dict) -> dict:
    """Apply this employee's stable dirt styles to its clean values → raw record."""
    s = Random(emp["_dirt_seed"])
    out: dict[str, object] = {}

    out["employee_id"] = str(emp["employee_id"]) if s.random() < 0.1 else emp["employee_id"]
    out["first_name"] = _pad(emp["first_name"], s)
    out["last_name"] = _pad(emp["last_name"], s)

    estyle = s.choices(["clean", "upper", "trail", "blank", "malformed"], weights=[78, 8, 6, 4, 4])[0]
    email = emp["email"]
    out["email"] = {
        "clean": email,
        "upper": email.upper(),
        "trail": email + " ",
        "blank": "",
        "malformed": email.replace("@", " at "),
    }[estyle]

    gstyle = s.choices(["clean", "title", "initial", "blank"], weights=[75, 12, 9, 4])[0]
    g = emp["gender"]
    out["gender"] = {
        "clean": g,
        "title": g.title(),
        "initial": g[0].upper() if g in ("female", "male") else g,
        "blank": "",
    }[gstyle]

    out["birth_date"] = _messy_date(
        emp["birth_date"], s.choices(["iso", "us", "dmy", "epoch", "na"], weights=[70, 12, 10, 5, 3])[0]
    )
    out["hire_date"] = _messy_date(
        emp["hire_date"], s.choices(["iso", "us", "dmy", "epoch", "blank"], weights=[70, 12, 10, 5, 3])[0]
    )

    dstyle = s.choices(["clean", "lower", "upper", "abbrev", "pad"], weights=[68, 12, 8, 6, 6])[0]
    dept = emp["department"]
    abbrev = {
        "Engineering": "ENG",
        "Human Resources": "HR",
        "Marketing": "MKTG",
        "Operations": "OPS",
        "Customer Support": "CS",
        "Finance": "FIN",
        "Product": "PROD",
    }
    out["department"] = {
        "clean": dept,
        "lower": dept.lower(),
        "upper": dept.upper(),
        "abbrev": abbrev.get(dept, dept[:3].upper()),
        "pad": f" {dept} ",
    }[dstyle]

    out["job_title"] = _pad(emp["job_title"], s)

    tstyle = s.choices(["clean", "space", "abbrev", "lower"], weights=[75, 10, 9, 6])[0]
    et = emp["employment_type"]
    et_abbrev = {"Full-time": "FT", "Part-time": "PT", "Contractor": "CTR", "Intern": "INT"}
    out["employment_type"] = {
        "clean": et,
        "space": et.replace("-", " "),
        "abbrev": et_abbrev.get(et, et),
        "lower": et.lower(),
    }[tstyle]

    sstyle = s.choices(["clean", "lower", "upper", "abbrev"], weights=[72, 12, 8, 8])[0]
    st = emp["employment_status"]
    st_abbrev = {"Active": "A", "Terminated": "term", "On Leave": "LOA"}
    out["employment_status"] = {
        "clean": st,
        "lower": st.lower(),
        "upper": st.upper(),
        "abbrev": st_abbrev.get(st, st),
    }[sstyle]

    salstyle = s.choices(
        ["float", "str_int", "br", "us", "neg", "zero", "blank"], weights=[68, 10, 8, 6, 3, 3, 2]
    )[0]
    sal = emp["salary"]
    out["salary"] = {
        "float": sal,
        "str_int": str(int(sal)),
        "br": _br_money(sal),
        "us": f"{sal:,.2f}",
        "neg": -sal,
        "zero": 0,
        "blank": "",
    }[salstyle]

    cstyle = s.choices(["clean", "lower", "symbol", "blank"], weights=[80, 8, 8, 4])[0]
    out["currency"] = {"clean": "BRL", "lower": "brl", "symbol": "R$", "blank": ""}[cstyle]

    mid = emp["manager_id"]
    if mid is None:
        out["manager_id"] = s.choice([None, 0, ""])
    else:
        mstyle = s.choices(["int", "str", "zero", "blank"], weights=[82, 10, 4, 4])[0]
        out["manager_id"] = {"int": mid, "str": str(mid), "zero": 0, "blank": ""}[mstyle]

    lstyle = s.choices(["clean", "pad", "na", "blank"], weights=[82, 8, 6, 4])[0]
    loc = emp["location"]
    out["location"] = {"clean": loc, "pad": f" {loc} ", "na": "N/A", "blank": ""}[lstyle]

    out["created_at"] = emp["created_at"]
    return out


def inject_duplicates(records: list[dict], rng: Random, ratio: float = 0.01) -> list[dict]:
    """Append a few conflicting duplicate rows (same employee_id) — a transport glitch."""
    if len(records) < 2:
        return list(records)
    out = list(records)
    for _ in range(max(1, int(len(records) * ratio))):
        dupe = dict(rng.choice(records))
        if isinstance(dupe.get("salary"), (int, float)) and dupe["salary"]:
            dupe["salary"] = round(float(dupe["salary"]) * 1.05, 2)
        out.append(dupe)
    return out


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #


def generate_month(year: int, month: int, cfg: GenConfig | None = None) -> list[dict]:
    """Generate the full messy roster snapshot for the given month (deterministic).

    Replays churn from cfg.start_date to (year, month), then serializes the
    resulting roster with stable per-employee messiness + a few duplicates.
    """
    cfg = cfg or GenConfig()
    target = date(year, month, 1)
    if target < cfg.start_date:
        raise ValueError(f"{target} is before start_date {cfg.start_date}")
    roster = _roster_for(target, cfg)
    rng = Random(f"{cfg.seed}:out:{target.isoformat()}")
    return inject_duplicates([serialize_messy(e) for e in roster], rng)
