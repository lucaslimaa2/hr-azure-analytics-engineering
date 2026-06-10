-- Step 10: the cleaning VIEW (reusable, no dynamic SQL) over ALL monthly snapshots.
--
-- Each raw/{yyyy}/{MM}/employees.json is a full-roster snapshot for that month.
-- This view cleans every field + derives columns across all months at once. The
-- per-month stored proc just SELECTs one month from it and CETAS-writes curated,
-- so the heavy logic stays in clean SQL (not a quoted dynamic-SQL string).
--
-- Key points:
--   1) BULK raw/*/*/*.json     reads every month at once.
--   2) files.filepath(1)/(2)   read year/month FROM the folder path -> snapshot_year/
--      month and reference_date (the snapshot month). There is no per-row date field.
--   3) dedupe PARTITION BY snapshot_year, snapshot_month, employee_id
--      (one row per employee per month — the same employee recurs across months).

USE hr_curated;
GO

CREATE OR ALTER VIEW dbo.vw_employees_clean AS
WITH raw_rows AS (
    SELECT
        files.filepath(1)                          AS part_year,   -- 1st wildcard = yyyy folder
        files.filepath(2)                          AS part_month,  -- 2nd wildcard = MM folder
        JSON_VALUE(r.value, '$.employee_id')       AS employee_id,
        JSON_VALUE(r.value, '$.first_name')        AS first_name,
        JSON_VALUE(r.value, '$.last_name')         AS last_name,
        JSON_VALUE(r.value, '$.email')             AS email,
        JSON_VALUE(r.value, '$.gender')            AS gender,
        JSON_VALUE(r.value, '$.birth_date')        AS birth_date,
        JSON_VALUE(r.value, '$.hire_date')         AS hire_date,
        JSON_VALUE(r.value, '$.department')        AS department,
        JSON_VALUE(r.value, '$.job_title')         AS job_title,
        JSON_VALUE(r.value, '$.employment_type')   AS employment_type,
        JSON_VALUE(r.value, '$.employment_status') AS employment_status,
        JSON_VALUE(r.value, '$.salary')            AS salary,
        JSON_VALUE(r.value, '$.currency')          AS currency,
        JSON_VALUE(r.value, '$.manager_id')        AS manager_id,
        JSON_VALUE(r.value, '$.location')          AS location,
        JSON_VALUE(r.value, '$.created_at')        AS created_at
    FROM OPENROWSET(
            BULK 'raw/*/*/*.json',
            DATA_SOURCE = 'lake',
            FORMAT='CSV', FIELDTERMINATOR='0x0b', FIELDQUOTE='0x0b',
            ROWTERMINATOR='0x0b', CODEPAGE='65001'
         ) WITH (doc NVARCHAR(MAX)) AS files
    CROSS APPLY OPENJSON(files.doc) AS r
),
sal1 AS (
    SELECT *, REPLACE(REPLACE(salary, 'R$', ''), ' ', '') AS sal_s FROM raw_rows
),
sal2 AS (
    SELECT *,
        CASE
            WHEN CHARINDEX(',', sal_s) > 0 AND CHARINDEX('.', sal_s) > 0 THEN
                CASE WHEN CHARINDEX(',', REVERSE(sal_s)) < CHARINDEX('.', REVERSE(sal_s))
                     THEN REPLACE(REPLACE(sal_s, '.', ''), ',', '.')
                     ELSE REPLACE(sal_s, ',', '') END
            WHEN CHARINDEX(',', sal_s) > 0 THEN REPLACE(sal_s, ',', '.')
            ELSE sal_s
        END AS sal_num
    FROM sal1
),
cleaned AS (
    SELECT
        CAST(part_year AS INT)                                AS snapshot_year,
        CAST(part_month AS INT)                               AS snapshot_month,
        TRY_CAST(employee_id AS INT)                          AS employee_id,
        TRIM(first_name)                                      AS first_name,
        TRIM(last_name)                                       AS last_name,
        CASE WHEN email LIKE '%@%' THEN LOWER(TRIM(email)) END AS email,
        CASE UPPER(TRIM(gender))
            WHEN 'FEMALE' THEN 'female' WHEN 'F' THEN 'female'
            WHEN 'MALE' THEN 'male'     WHEN 'M' THEN 'male'
            WHEN 'OTHER' THEN 'other'   ELSE 'unknown' END     AS gender,
        CASE
            WHEN birth_date LIKE '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]' THEN TRY_CONVERT(date, birth_date, 23)
            WHEN birth_date LIKE '%/%'                                        THEN TRY_CONVERT(date, birth_date, 101)
            WHEN birth_date LIKE '[0-9][0-9]-[0-9][0-9]-[0-9][0-9][0-9][0-9]' THEN TRY_CONVERT(date, birth_date, 105)
            WHEN birth_date NOT LIKE '%[^0-9]%' AND LEN(birth_date) > 0       THEN DATEADD(second, TRY_CAST(birth_date AS BIGINT), '1970-01-01')
        END                                                    AS birth_date,
        CASE
            WHEN hire_date LIKE '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'  THEN TRY_CONVERT(date, hire_date, 23)
            WHEN hire_date LIKE '%/%'                                         THEN TRY_CONVERT(date, hire_date, 101)
            WHEN hire_date LIKE '[0-9][0-9]-[0-9][0-9]-[0-9][0-9][0-9][0-9]'  THEN TRY_CONVERT(date, hire_date, 105)
            WHEN hire_date NOT LIKE '%[^0-9]%' AND LEN(hire_date) > 0         THEN DATEADD(second, TRY_CAST(hire_date AS BIGINT), '1970-01-01')
        END                                                    AS hire_date,
        CASE UPPER(TRIM(department))
            WHEN 'ENGINEERING' THEN 'Engineering' WHEN 'ENG' THEN 'Engineering'
            WHEN 'SALES' THEN 'Sales'
            WHEN 'HUMAN RESOURCES' THEN 'Human Resources' WHEN 'HR' THEN 'Human Resources'
            WHEN 'FINANCE' THEN 'Finance' WHEN 'FIN' THEN 'Finance'
            WHEN 'MARKETING' THEN 'Marketing' WHEN 'MKTG' THEN 'Marketing'
            WHEN 'OPERATIONS' THEN 'Operations' WHEN 'OPS' THEN 'Operations'
            WHEN 'CUSTOMER SUPPORT' THEN 'Customer Support' WHEN 'CS' THEN 'Customer Support'
            WHEN 'PRODUCT' THEN 'Product' WHEN 'PROD' THEN 'Product'
            ELSE 'Unknown' END                                 AS department,
        TRIM(job_title)                                        AS job_title,
        CASE UPPER(REPLACE(TRIM(employment_type), '-', ' '))
            WHEN 'FULL TIME' THEN 'Full-time' WHEN 'FT' THEN 'Full-time'
            WHEN 'PART TIME' THEN 'Part-time' WHEN 'PT' THEN 'Part-time'
            WHEN 'CONTRACTOR' THEN 'Contractor' WHEN 'CTR' THEN 'Contractor'
            WHEN 'INTERN' THEN 'Intern' WHEN 'INT' THEN 'Intern'
            ELSE 'Unknown' END                                 AS employment_type,
        CASE UPPER(TRIM(employment_status))
            WHEN 'ACTIVE' THEN 'Active' WHEN 'A' THEN 'Active'
            WHEN 'TERMINATED' THEN 'Terminated' WHEN 'TERM' THEN 'Terminated'
            WHEN 'ON LEAVE' THEN 'On Leave' WHEN 'LOA' THEN 'On Leave'
            ELSE 'Unknown' END                                 AS employment_status,
        CASE WHEN TRY_CAST(sal_num AS DECIMAL(12,2)) > 0
             THEN TRY_CAST(sal_num AS DECIMAL(12,2)) END        AS salary,
        CASE WHEN UPPER(TRIM(currency)) IN ('BRL','R$') OR TRIM(currency) = '' THEN 'BRL'
             ELSE UPPER(TRIM(currency)) END                     AS currency,
        NULLIF(TRY_CAST(manager_id AS INT), 0)                 AS manager_id,
        CASE WHEN TRIM(location) IN ('', 'N/A', '-') THEN NULL ELSE TRIM(location) END AS location,
        TRY_CONVERT(datetime2, created_at, 127)                AS ingested_at
    FROM sal2
),
snap AS (   -- the "as of" date = this row's own month-end
    SELECT *, EOMONTH(DATEFROMPARTS(snapshot_year, snapshot_month, 1)) AS snapshot_date
    FROM cleaned
),
enriched AS (
    SELECT *,
        CONCAT(first_name, ' ', last_name)                     AS full_name,
        DATEFROMPARTS(snapshot_year, snapshot_month, 1)        AS reference_date,
        DATEDIFF(YEAR, birth_date, snapshot_date)
            - CASE WHEN (MONTH(snapshot_date) < MONTH(birth_date))
                     OR (MONTH(snapshot_date) = MONTH(birth_date) AND DAY(snapshot_date) < DAY(birth_date))
                   THEN 1 ELSE 0 END                           AS age,
        DATEDIFF(MONTH, hire_date, snapshot_date)              AS tenure_months
    FROM snap
),
ranked AS (
    SELECT *,
        ROW_NUMBER() OVER (PARTITION BY snapshot_year, snapshot_month, employee_id
                           ORDER BY ingested_at DESC) AS rn
    FROM enriched
)
SELECT
    snapshot_year, snapshot_month, reference_date,
    employee_id,
    first_name, last_name, full_name, email, gender,
    birth_date, age, hire_date, tenure_months,
    department, job_title, employment_type, employment_status,
    salary, currency, manager_id, location, ingested_at
FROM ranked
WHERE rn = 1;
GO
