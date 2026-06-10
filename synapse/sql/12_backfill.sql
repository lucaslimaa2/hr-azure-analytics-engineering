-- Step 12: backfill curated for every month we've landed (Jan-May 2026).
--
-- One EXEC per month. Each call CETAS-writes curated/{yyyy}/{MM}/ from the view.
-- In production the pipeline runs ONE of these per monthly trigger; this script
-- just does all five at once for the initial load.
--
-- Pre-req: curated/2026/** is empty (CETAS won't overwrite). We cleared it during
-- the monthly rebuild, so these run clean.

USE hr_curated;
GO

EXEC dbo.usp_transform_month @year = 2026, @month = 1;
EXEC dbo.usp_transform_month @year = 2026, @month = 2;
EXEC dbo.usp_transform_month @year = 2026, @month = 3;
EXEC dbo.usp_transform_month @year = 2026, @month = 4;
EXEC dbo.usp_transform_month @year = 2026, @month = 5;
GO

-- Quick check: row count per month (should match the distinct headcount, dupes removed).
SELECT snapshot_year, snapshot_month, COUNT(*) AS employees
FROM dbo.vw_employees_clean
GROUP BY snapshot_year, snapshot_month
ORDER BY snapshot_year, snapshot_month;
