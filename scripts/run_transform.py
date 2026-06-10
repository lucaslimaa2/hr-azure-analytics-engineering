"""Run the monthly transform on the serverless pool (the CI transform step).

Connects to the Synapse serverless SQL endpoint as the `hr-github-actions` service
principal (an Azure AD access token from DefaultAzureCredential — the same AZURE_* env
vars) and executes `usp_transform_month`, which CETAS-writes curated/{yyyy}/{MM}/.

Note: the lake read/write inside the proc (OPENROWSET on raw, CETAS to curated) is done
by the Synapse workspace managed identity via the external data source's scoped
credential — NOT by this connection. This connection only needs to *run the proc*.

CETAS won't overwrite, so we first clear this month's curated folder (as the SP, which
has Storage Blob Data Contributor) to keep the step idempotent / re-runnable.

Usage:  python scripts/run_transform.py --year 2026 --month 6
"""

from __future__ import annotations

import argparse
import os
import struct

import pyodbc
from azure.identity import DefaultAzureCredential
from azure.storage.filedatalake import DataLakeServiceClient

SQL_COPT_SS_ACCESS_TOKEN = 1256  # ODBC connection attribute: supply an AAD access token


def main() -> None:
    ap = argparse.ArgumentParser(description="Run usp_transform_month on serverless SQL.")
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--month", type=int, required=True)
    args = ap.parse_args()

    mm = f"{args.month:02d}"
    credential = DefaultAzureCredential()

    # 1) Clear this month's curated folder so CETAS can write fresh (idempotent re-runs).
    lake = DataLakeServiceClient(os.environ["STORAGE_ACCOUNT_URL"], credential)
    curated_dir = lake.get_file_system_client("curated").get_directory_client(f"{args.year}/{mm}")
    if curated_dir.exists():
        curated_dir.delete_directory()
        print(f"cleared curated/{args.year}/{mm} (for a clean CETAS write)")

    # 2) Get an Azure AD token for Azure SQL, as the service principal.
    token = credential.get_token("https://database.windows.net/.default").token
    token_bytes = token.encode("utf-16-le")
    token_struct = struct.pack(f"<I{len(token_bytes)}s", len(token_bytes), token_bytes)

    # 3) Connect to the serverless pool with that token (no SQL password) and run the proc.
    server = os.environ["SQL_SERVER"]
    database = os.environ.get("SQL_DATABASE", "hr_curated")
    conn_str = (
        "Driver={ODBC Driver 18 for SQL Server};"
        f"Server={server};Database={database};Encrypt=yes;TrustServerCertificate=no;"
    )
    with pyodbc.connect(
        conn_str, attrs_before={SQL_COPT_SS_ACCESS_TOKEN: token_struct}, autocommit=True
    ) as conn:
        cur = conn.cursor()
        print(f"running usp_transform_month @year={args.year} @month={args.month} ...")
        cur.execute("EXEC dbo.usp_transform_month @year = ?, @month = ?", args.year, args.month)
        print(f"[ok] transform completed -> curated/{args.year}/{mm}/")


if __name__ == "__main__":
    main()
