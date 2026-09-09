from __future__ import annotations

from datetime import date

from app.engine import classify_salary_position, recommend_all, recommend_employee
from app.ingest import read_workbook
from app.models import (
    CorrectionRule,
    Employee,
    IncrementRule,
    SalaryBand,
    SalaryPosition,
)
from app.sample_workbook import build_sample_workbook


def _employee(**overrides) -> Employee:
    data = dict(
        employee_id="1001",
        employee_name="Ananya Rao",
        department="Technology",
        grade="A1",
        designation="Software Engineer",
        current_salary=10.0,
        performance_rating=4,
        date_of_joining=date(2023, 4, 10),
        current_grade_since=date(2024, 4, 1),
        years_at_level=2,
        total_years_experience=4.5,
        location="Bengaluru",
        reporting_manager="Vikram Shah",
        reporting_partner="Neha Kapoor",
        employment_status="Active",
    )
    data.update(overrides)
    return Employee(**data)


BANDS = [
    SalaryBand("Technology", "A1", 2, 11, 14, 20, "2 Years"),
]
INCREMENTS = [
    IncrementRule("A1", 5, 0.15),
    IncrementRule("A1", 4, 0.10),
    IncrementRule("A1", 3, 0.07),
    IncrementRule("A1", 2, 0.03),
    IncrementRule("A1", 1, 0.00),
]
CORRECTIONS = [
    CorrectionRule(0.00, 0.80, 0.08),
    CorrectionRule(0.80, 0.90, 0.05),
    CorrectionRule(0.90, 1.00, 0.02),
    CorrectionRule(1.00, 999, 0.00),
]


def test_spec_example_ten_lpa_rating_four():
    result = recommend_employee(_employee(), BANDS, INCREMENTS, CORRECTIONS)
    assert result.compa_ratio == 0.7143  # 10 / 14 rounded to 4 dp
    assert result.salary_position == SalaryPosition.BELOW_MINIMUM.value
    assert result.increment_pct == 0.10
    assert result.correction_pct == 0.08
    assert result.total_increase_pct == 0.18
    assert result.recommended_salary == 11.8


def test_compa_boundary_uses_half_open_range():
    at_eighty = recommend_employee(_employee(current_salary=11.2), BANDS, INCREMENTS, CORRECTIONS)
    # 11.2 / 14 = 0.80 exactly → 5% bucket, not 8%
    assert at_eighty.compa_ratio == 0.8
    assert at_eighty.correction_pct == 0.05

    just_below = recommend_employee(_employee(current_salary=11.19), BANDS, INCREMENTS, CORRECTIONS)
    assert just_below.compa_ratio < 0.80
    assert just_below.correction_pct == 0.08


def test_at_median_gets_zero_correction():
    result = recommend_employee(_employee(current_salary=14), BANDS, INCREMENTS, CORRECTIONS)
    assert result.compa_ratio == 1.0
    assert result.correction_pct == 0.0
    assert result.salary_position == SalaryPosition.MARKET_ALIGNED.value
    assert result.increment_pct == 0.10
    assert result.recommended_salary == 15.4


def test_above_band_and_below_median_positions():
    above = classify_salary_position(21, 11, 14, 20)
    below_min = classify_salary_position(10, 11, 14, 20)
    below_med = classify_salary_position(12, 11, 14, 20)
    above_med = classify_salary_position(16, 11, 14, 20)
    aligned = classify_salary_position(14.2, 11, 14, 20)
    assert above == SalaryPosition.ABOVE_BAND
    assert below_min == SalaryPosition.BELOW_MINIMUM
    assert below_med == SalaryPosition.BELOW_MEDIAN
    assert above_med == SalaryPosition.ABOVE_MEDIAN
    assert aligned == SalaryPosition.MARKET_ALIGNED


def test_missing_band_applies_increment_only():
    result = recommend_employee(
        _employee(department="Legal"),
        BANDS,
        INCREMENTS,
        CORRECTIONS,
    )
    assert result.increment_pct == 0.10
    assert result.correction_pct == 0.0
    assert result.recommended_salary == 11.0
    assert any("band not found" in flag.lower() for flag in result.flags)


def test_sample_workbook_round_trip():
    employees, increments, bands, corrections, warnings, counts = read_workbook(build_sample_workbook())
    assert counts["Employee_Master"] == 28
    assert counts["Increment_Grid"] == 25
    assert not warnings
    reports = recommend_all(employees, bands, increments, corrections)
    by_id = {row.employee_id: row for row in reports}
    spec = by_id["1001"]
    assert spec.increment_pct == 0.10
    assert spec.correction_pct == 0.08
    assert spec.recommended_salary == 11.8
    assert spec.compa_ratio == 0.7143
    assert spec.increment_amount == 1.0
    assert spec.correction_amount == 0.8
    assert any("regardless of rating" in flag for flag in spec.flags)
    mid = by_id["1007"]
    assert 0.80 <= mid.compa_ratio < 0.90
    assert mid.correction_pct == 0.05
    high = by_id["1006"]
    assert high.salary_position == "Above Band"
    assert high.correction_pct == 0.0
    assert high.increment_pct == 0.07
    low = by_id["1023"]
    assert low.performance_rating == 1
    assert low.salary_position == "Below Minimum"
    assert low.increment_pct == 0.0
    assert low.correction_pct == 0.08
    assert low.recommended_salary == 11.34
