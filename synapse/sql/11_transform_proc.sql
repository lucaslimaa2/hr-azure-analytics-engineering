-- Step 11: the per-month transform stored procedure (thin materializer).
--
-- All the cleaning/modeling lives in dbo.vw_employees_clean (step 10). This proc
-- just picks ONE month out of that view and CETAS-writes it to curated/{yyyy}/{MM}/
-- as parquet. The pipeline calls it once per monthly run:
--     EXEC dbo.usp_transform_month @year = 2026, @month = 3;
--
-- Why dynamic SQL here: CETAS needs the target table NAME and LOCATION as literal
-- text — they cannot be @parameters. So we build a SHORT "CREATE EXTERNAL TABLE ...
-- AS SELECT * FROM the view WHERE this month" string and run it. The heavy logic is
-- NOT in the string (it's in the view) — only this thin wrapper is.
--
-- Re-run note: CETAS cannot overwrite existing parquet. To re-run a month you must
-- first delete curated/{yyyy}/{MM}/ in the lake (dropping the external table only
-- removes the metadata, not the files). The pipeline clears the folder before EXEC.

USE hr_curated;
GO

CREATE OR ALTER PROCEDURE dbo.usp_transform_month
    @year  INT,
    @month INT
AS
BEGIN
    SET NOCOUNT ON;

    -- Build the per-month names from the parameters.
    DECLARE @mm  CHAR(2)      = RIGHT('0' + CAST(@month AS VARCHAR(2)), 2);   -- 3 -> '03'
    DECLARE @tbl SYSNAME      = CONCAT('curated_employees_', @year, '_', @mm); -- registration name
    DECLARE @loc VARCHAR(200) = CONCAT('curated/', @year, '/', @mm, '/');      -- where parquet lands
    DECLARE @sql NVARCHAR(MAX);

    -- 1) Drop this month's previous external-table registration (metadata only).
    IF OBJECT_ID(@tbl) IS NOT NULL
    BEGIN
        SET @sql = N'DROP EXTERNAL TABLE ' + QUOTENAME(@tbl) + N';';
        EXEC sp_executesql @sql;
    END

    -- 2) CETAS: write this month's clean rows to curated as parquet, and register
    --    the external table you can SELECT from afterwards.
    SET @sql = N'
        CREATE EXTERNAL TABLE ' + QUOTENAME(@tbl) + N'
        WITH (LOCATION = ''' + @loc + N''', DATA_SOURCE = lake, FILE_FORMAT = parquet_fmt)
        AS
        SELECT *
        FROM dbo.vw_employees_clean
        WHERE snapshot_year  = ' + CAST(@year  AS VARCHAR(4)) + N'
          AND snapshot_month = ' + CAST(@month AS VARCHAR(2)) + N';';
    EXEC sp_executesql @sql;
END
GO
