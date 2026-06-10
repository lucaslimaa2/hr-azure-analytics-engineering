"""Partition-path building from the run's month date."""

from datetime import date

import pytest
from shared import partitions as p


def test_month_dir_zero_pads_month():
    assert p.month_dir("2026-06-08") == "2026/06"
    assert p.month_dir(date(2026, 1, 1)) == "2026/01"


def test_raw_path_compose():
    # How storage.write_raw builds the path inside the raw filesystem.
    d = "2026-03-01"
    assert f"{p.month_dir(d)}/{p.RAW_FILE}" == "2026/03/employees.json"


def test_parse_date_accepts_iso_string_and_date():
    assert p.parse_date("2026-06-08") == date(2026, 6, 8)
    assert p.parse_date(date(2026, 6, 8)) == date(2026, 6, 8)


def test_parse_date_rejects_bad_format():
    with pytest.raises(ValueError):
        p.parse_date("06/08/2026")
