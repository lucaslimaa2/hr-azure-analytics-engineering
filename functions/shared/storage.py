"""ADLS Gen2 writer — the only Python module that touches the data lake.

Auth is via ``DefaultAzureCredential``: locally it uses your ``az login`` session;
in Azure it uses the Function App's managed identity. No keys or connection
strings in code.

Since the transform runs as serverless SQL (it reads raw and writes curated
itself), Python only ever **writes raw**. ``write_raw`` refuses to overwrite an
existing weekly file — raw is immutable.
"""

from __future__ import annotations

import json

from azure.identity import DefaultAzureCredential
from azure.storage.filedatalake import DataLakeServiceClient

from . import partitions
from .config import Config


class RawAlreadyExistsError(RuntimeError):
    """Raised when a weekly raw file already exists — raw is immutable."""


class Storage:
    """A thin writer for the lake's raw zone."""

    def __init__(self, config: Config, credential=None):
        cred = credential or DefaultAzureCredential()
        self._service = DataLakeServiceClient(account_url=config.storage_account_url, credential=cred)

    def _fs(self, zone: str):
        return self._service.get_file_system_client(zone)

    def write_raw(self, run_date, records: list[dict]) -> str:
        """Write the month's full-roster snapshot to ``raw/{yyyy}/{MM}/employees.json``.

        Refuses to overwrite an existing file — raw partitions are immutable.
        Returns the path written.
        """
        path = f"{partitions.month_dir(run_date)}/{partitions.RAW_FILE}"
        file_client = self._fs(partitions.RAW).get_file_client(path)

        if file_client.exists():
            raise RawAlreadyExistsError(f"raw/{path} already exists; raw is immutable")

        # Immutability is enforced by the exists() check above. We then write with
        # overwrite=True because on ADLS Gen2 that reliably *creates* the file (and
        # its parent {yyyy}/{MM}/ directories); overwrite=False tries to append to a
        # not-yet-created path and fails with PathNotFound.
        data = json.dumps(records, ensure_ascii=False, indent=2).encode("utf-8")
        file_client.upload_data(data, overwrite=True)
        return f"{partitions.RAW}/{path}"
