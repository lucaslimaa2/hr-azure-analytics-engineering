"""Build ``{zone}/{yyyy}/{MM}/`` partition paths from the run's month date.

The Synapse monthly trigger supplies the run's month (a date). Each month gets
one full-roster snapshot file: ``{zone}/{yyyy}/{MM}/employees.json``. Month is
zero-padded (e.g. ``2026/01``). Dates are never hardcoded.
"""

from __future__ import annotations

from datetime import date

RAW = "raw"
CURATED = "curated"
ZONES = (RAW, CURATED)
RAW_FILE = "employees.json"  # one monthly full-roster snapshot per partition


def parse_date(value: str | date) -> date:
    """Coerce an ISO ``YYYY-MM-DD`` string (or date) into a date."""
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"date must be ISO YYYY-MM-DD, got {value!r}") from exc


def month_dir(value: str | date) -> str:
    """Partition directory *within* a zone, e.g. ``2026/01``."""
    d = parse_date(value)
    return f"{d.year:04d}/{d.month:02d}"
