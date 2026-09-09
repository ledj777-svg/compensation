from __future__ import annotations

from statistics import median

from app.models import CorrectionRule, Employee, IncrementRule, SalaryBand
from app.parsing import normalize_grade

DEFAULT_RATING_INCREMENT = {
    5: 0.15,
    4: 0.10,
    3: 0.07,
    2: 0.03,
    1: 0.00,
}

DEFAULT_GRADE_BANDS = {
    "A1": {
        0: (9.0, 12.0, 16.0),
        1: (10.0, 13.0, 18.0),
        2: (11.0, 14.0, 20.0),
        3: (12.0, 15.5, 22.0),
        4: (12.5, 16.0, 23.0),
        5: (13.0, 17.0, 24.0),
    },
    "A2": {
        2: (16.0, 20.0, 28.0),
        3: (17.0, 21.0, 30.0),
        4: (18.0, 22.0, 32.0),
        5: (19.0, 23.0, 34.0),
    },
    "A3": {
        2: (18.0, 22.0, 30.0),
        3: (19.0, 23.0, 32.0),
        4: (20.0, 24.0, 34.0),
        5: (21.0, 25.0, 36.0),
    },
    "A4": {
        2: (20.0, 24.0, 32.0),
        3: (21.0, 25.0, 34.0),
        4: (22.0, 26.0, 36.0),
        5: (23.0, 27.0, 38.0),
    },
    "B1": {
        2: (22.0, 28.0, 36.0),
        3: (23.0, 29.0, 38.0),
        4: (24.0, 30.0, 40.0),
        5: (25.0, 31.0, 42.0),
    },
    "B2": {
        4: (26.0, 32.0, 42.0),
        5: (27.0, 33.0, 44.0),
    },
    "C1": {
        4: (30.0, 38.0, 50.0),
        5: (32.0, 40.0, 55.0),
    },
}

DEFAULT_CORRECTION_RULES = [
    CorrectionRule(0.00, 0.80, 0.08),
    CorrectionRule(0.80, 0.90, 0.05),
    CorrectionRule(0.90, 1.00, 0.02),
    CorrectionRule(1.00, 999, 0.00),
]


def default_increment_rules(employees: list[Employee]) -> list[IncrementRule]:
    grades = {normalize_grade(employee.grade) or "A1" for employee in employees}
    grades.update(DEFAULT_GRADE_BANDS)
    rules: list[IncrementRule] = []
    for grade in sorted(grades):
        for rating, pct in DEFAULT_RATING_INCREMENT.items():
            rules.append(IncrementRule(grade=grade, performance_rating=rating, increment_pct=pct))
    return rules


def _band_points(grade: str) -> dict[int, tuple[float, float, float]]:
    return DEFAULT_GRADE_BANDS.get(normalize_grade(grade), DEFAULT_GRADE_BANDS["A1"])


def _pick_points(grade: str, years: float | None) -> tuple[float, float, float, float]:
    points = _band_points(grade)
    if years is None:
        year_key = min(points)
        return float(year_key), *points[year_key]
    closest = min(points, key=lambda value: abs(value - years))
    return float(closest), *points[closest]


def _salary_stats(values: list[float]) -> tuple[float, float, float] | None:
    salaries = [float(value) for value in values if value is not None]
    if len(salaries) < 3:
        return None
    return (round(min(salaries), 4), round(float(median(salaries)), 4), round(max(salaries), 4))


def _empirical_points(employee: Employee, employees: list[Employee]) -> tuple[float, float, float] | None:
    years = employee.years_at_level
    grade = normalize_grade(employee.grade)
    dept = employee.department
    same_years = [item.current_salary for item in employees if item.years_at_level == years]
    same_grade_years = [
        item.current_salary
        for item in employees
        if item.years_at_level == years and normalize_grade(item.grade) == grade
    ]
    same_dept_grade_years = [
        item.current_salary
        for item in employees
        if item.years_at_level == years
        and normalize_grade(item.grade) == grade
        and item.department == dept
    ]
    return (
        _salary_stats(same_dept_grade_years)
        or _salary_stats(same_grade_years)
        or _salary_stats(same_years)
    )


def default_salary_bands(employees: list[Employee]) -> list[SalaryBand]:
    bands: list[SalaryBand] = []
    seen: set[tuple[str, str, float | None]] = set()
    for employee in employees:
        key = (employee.department, employee.grade, employee.years_at_level)
        if key in seen:
            continue
        seen.add(key)
        empirical = _empirical_points(employee, employees)
        if empirical:
            minimum, mid, maximum = empirical
            years = float(employee.years_at_level if employee.years_at_level is not None else 0)
        else:
            year_key, minimum, mid, maximum = _pick_points(employee.grade, employee.years_at_level)
            years = employee.years_at_level if employee.years_at_level is not None else year_key
        bands.append(
            SalaryBand(
                department=employee.department or "General",
                grade=employee.grade or "A1",
                years_at_level=float(years),
                min_salary=minimum,
                median_salary=mid,
                max_salary=maximum,
                raw_years_label=f"{years:g} Years",
            )
        )
    return bands


def ensure_coverage(
    employees: list[Employee],
    increment_rules: list[IncrementRule],
    salary_bands: list[SalaryBand],
    correction_rules: list[CorrectionRule],
) -> tuple[list[IncrementRule], list[SalaryBand], list[CorrectionRule]]:
    """Fill missing grades/bands so every employee can get a compa, increment, and position."""
    from app.engine import find_salary_band

    if not correction_rules:
        correction_rules = list(DEFAULT_CORRECTION_RULES)

    covered = {
        (normalize_grade(rule.grade), rule.performance_rating) for rule in increment_rules
    }
    extra_rules = list(increment_rules)
    grades = {normalize_grade(employee.grade) or "A1" for employee in employees}
    for grade in grades:
        for rating, pct in DEFAULT_RATING_INCREMENT.items():
            if (grade, rating) not in covered:
                extra_rules.append(
                    IncrementRule(grade=grade, performance_rating=rating, increment_pct=pct)
                )
                covered.add((grade, rating))

    extra_bands = list(salary_bands)
    for employee in employees:
        if find_salary_band(employee, extra_bands) is not None:
            continue
        empirical = _empirical_points(employee, employees)
        if empirical:
            minimum, mid, maximum = empirical
            years = float(employee.years_at_level if employee.years_at_level is not None else 0)
        else:
            year_key, minimum, mid, maximum = _pick_points(employee.grade, employee.years_at_level)
            years = employee.years_at_level if employee.years_at_level is not None else year_key
        extra_bands.append(
            SalaryBand(
                department=employee.department or "General",
                grade=employee.grade or "A1",
                years_at_level=float(years),
                min_salary=minimum,
                median_salary=mid,
                max_salary=maximum,
                raw_years_label=f"{years:g} Years",
            )
        )
    return extra_rules, extra_bands, correction_rules


def apply_defaults(
    employees: list[Employee],
    increment_rules: list[IncrementRule],
    salary_bands: list[SalaryBand],
    correction_rules: list[CorrectionRule],
) -> tuple[list[IncrementRule], list[SalaryBand], list[CorrectionRule], list[str]]:
    used: list[str] = []
    if not increment_rules:
        increment_rules = default_increment_rules(employees)
        used.append("Increment_Grid")
    if not salary_bands:
        salary_bands = default_salary_bands(employees)
        used.append("Salary_Band")
    if not correction_rules:
        correction_rules = list(DEFAULT_CORRECTION_RULES)
        used.append("Salary_Correction_Rules")
    return increment_rules, salary_bands, correction_rules, used
