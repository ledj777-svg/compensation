from __future__ import annotations

from app.engine import recommend_employee
from app.models import CorrectionRule
from tests.test_engine import BANDS, CORRECTIONS, INCREMENTS, _employee


def test_rule1_below_min_gets_correction_even_if_rating_is_one():
    result = recommend_employee(
        _employee(performance_rating=1, current_salary=10),
        BANDS,
        INCREMENTS,
        CORRECTIONS,
    )
    assert result.increment_pct == 0.0
    assert result.correction_pct == 0.08
    assert result.total_increase_pct == 0.08
    assert result.recommended_salary == 10.8
    assert any("regardless of rating" in flag for flag in result.flags)


def test_rule1_forces_correction_if_rules_would_pay_zero():
    zero_rules = [CorrectionRule(0.00, 999, 0.00)]
    result = recommend_employee(
        _employee(performance_rating=1, current_salary=10),
        BANDS,
        INCREMENTS,
        zero_rules,
    )
    assert result.salary_position == "Below Minimum"
    assert result.correction_pct > 0
    assert result.recommended_salary >= 11


def test_rule2_above_max_blocks_correction_even_if_grid_would_pay():
    always_correct = [CorrectionRule(0.00, 999, 0.08)]
    result = recommend_employee(
        _employee(current_salary=21, performance_rating=4),
        BANDS,
        INCREMENTS,
        always_correct,
    )
    assert result.salary_position == "Above Band"
    assert result.correction_pct == 0.0
    assert result.increment_pct == 0.10
    assert result.recommended_salary == 23.1
    assert any("correction withheld" in flag.lower() for flag in result.flags)


def test_rule3_same_dept_grade_years_share_the_same_band():
    low = recommend_employee(_employee(employee_id="1001", current_salary=10), BANDS, INCREMENTS, CORRECTIONS)
    high = recommend_employee(_employee(employee_id="1002", current_salary=16), BANDS, INCREMENTS, CORRECTIONS)
    assert low.band_min == high.band_min == 11
    assert low.band_median == high.band_median == 14
    assert low.band_max == high.band_max == 20
    assert low.band_years_matched == high.band_years_matched == 2
