/* ---------------------------------------------------------------------------
   Step 8 — one-time setup objects for the serverless SQL transform. Allow the transform steps to write curated parquet automatically

   Run once in the Built-in (serverless) pool. Creates:
     - database  hr_curated      (CETAS needs a user DB, not master)
     - credential lake_cred       (auth to the lake via the workspace identity)
     - data source lake           (named pointer to the lake + the credential)
     - file format parquet_fmt    (CETAS output = parquet)

   The workspace managed identity already has Storage Blob Data Contributor on
   the lake (granted in Terraform), so 'Managed Identity' just works — no secrets.
   IF NOT EXISTS guards make this safe to re-run.
--------------------------------------------------------------------------- */

-- 1) database (must be its own batch)
IF DB_ID('hr_curated') IS NULL
    CREATE DATABASE hr_curated;
GO

USE hr_curated;
GO

-- 2) master key: required before creating ANY scoped credential. It encrypts the
--    credential store. (Even managed-identity creds need it to exist.) The password
--    only protects this local key store; the credential itself holds no secret.
--    Set your OWN strong password at deploy time — never commit a real one.
IF NOT EXISTS (SELECT 1 FROM sys.symmetric_keys WHERE name = '##MS_DatabaseMasterKey##')
    CREATE MASTER KEY ENCRYPTION BY PASSWORD = '<choose-a-strong-password>';
GO

-- 3) credential: the serverless pool authenticates to the lake AS the workspace
--    managed identity (which has the data role). Managed Identity = no secret stored.
IF NOT EXISTS (SELECT 1 FROM sys.database_scoped_credentials WHERE name = 'lake_cred')
    CREATE DATABASE SCOPED CREDENTIAL lake_cred WITH IDENTITY = 'Managed Identity';
GO

-- 4) external data source: a named handle for the lake (account root). Paths like
--    'raw/...' and 'curated/...' are resolved relative to it (first segment = container).
IF NOT EXISTS (SELECT 1 FROM sys.external_data_sources WHERE name = 'lake')
    CREATE EXTERNAL DATA SOURCE lake WITH (
        LOCATION   = 'https://hrdatalake780hz7.dfs.core.windows.net',
        CREDENTIAL = lake_cred
    );
GO

-- 5) external file format: CETAS writes parquet
IF NOT EXISTS (SELECT 1 FROM sys.external_file_formats WHERE name = 'parquet_fmt')
    CREATE EXTERNAL FILE FORMAT parquet_fmt WITH (FORMAT_TYPE = PARQUET);
GO
