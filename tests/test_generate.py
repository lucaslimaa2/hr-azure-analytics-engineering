"""The in-pipeline source generator: deterministic monthly full-roster snapshots."""

from datetime import date

import pytest
from shared.generate import GenConfig, generate_month

CFG = GenConfig(start_date=date(2026, 1, 1), seed=42, start_count=50, hires_per_month=20, term_rate=0.1)


def _ids(records):
    return {int(r["employee_id"]) for r in records}


def test_deterministic_same_month_identical():
    assert generate_month(2026, 2, CFG) == generate_month(2026, 2, CFG)


def test_first_month_is_start_count():
    assert _ids(generate_month(2026, 1, CFG)) == set(range(1, 51))  # ids 1..50


def test_carry_forward_plus_hires_minus_terms():
    m1 = _ids(generate_month(2026, 1, CFG))
    m2 = _ids(generate_month(2026, 2, CFG))
    carried = m1 & m2
    assert 0 < len(carried) < len(m1)  # most people carry forward, a few are terminated
    assert len(m2 - m1) == 20  # exactly hires_per_month brand-new ids
    assert len(m2) > len(m1)  # net headcount grows (20 hired > ~5 left)


def test_terminated_people_stay_gone():
    m1 = _ids(generate_month(2026, 1, CFG))
    m2 = _ids(generate_month(2026, 2, CFG))
    m3 = _ids(generate_month(2026, 3, CFG))
    left_in_feb = m1 - m2  # terminated between Jan and Feb
    assert left_in_feb  # someone left
    assert not (left_in_feb & m3)  # and they never reappear


def test_before_start_rejected():
    with pytest.raises(ValueError):
        generate_month(2025, 12, CFG)


def test_defects_are_present():
    recs = generate_month(2026, 1, CFG)
    canonical = {
        "Engineering",
        "Sales",
        "Human Resources",
        "Finance",
        "Marketing",
        "Operations",
        "Customer Support",
        "Product",
    }
    messy_dept = any(r["department"] not in canonical for r in recs)
    str_salary = any(isinstance(r["salary"], str) for r in recs)
    assert messy_dept or str_salary
