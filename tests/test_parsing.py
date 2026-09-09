from __future__ import annotations

from app.parsing import parse_percent, parse_salary_lpa, parse_years


def test_parse_percent_variants():
    assert parse_percent("15%") == 0.15
    assert parse_percent(15) == 0.15
    assert parse_percent(0.15) == 0.15
    assert parse_percent("10") == 0.10
    assert parse_percent(0) == 0.0


def test_parse_salary_lpa():
    assert parse_salary_lpa("11 LPA") == 11
    assert parse_salary_lpa(11) == 11
    assert parse_salary_lpa(1_100_000) == 11
    assert parse_salary_lpa("14") == 14


def test_parse_years():
    assert parse_years("2 Years") == 2
    assert parse_years(2) == 2
    assert parse_years("0-2") == 2
    assert parse_years("5+") == 5
