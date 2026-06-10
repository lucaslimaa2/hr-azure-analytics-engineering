-- Step 13: the SERVING view over the curated zone (the BI front door).
--
-- vw_employees_clean (step 10) reads RAW and does the heavy cleaning. This view sits
-- one layer later: it reads the already-clean CURATED parquet and simply consolidates
-- every monthly partition into one queryable object. No cleaning here — that work is
-- already materialized in curated.
--
-- It is a deploy-time object (created once, like the clean view and the proc). It is NOT
-- part of the monthly pipeline: because it globs curated/*/*, it automatically includes
-- each new month as the pipeline writes it. Power BI connects to this single view and
-- filters by reference_date / snapshot_month.

USE hr_curated;
GO

CREATE OR ALTER VIEW dbo.curated_employees_all AS
SELECT c.*
FROM OPENROWSET(
        BULK 'curated/*/*/*.parquet',
        DATA_SOURCE = 'lake',
        FORMAT = 'PARQUET'
     ) AS c;
GO
