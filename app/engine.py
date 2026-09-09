from __future__ import annotations

from app.models import (
    MARKET_ALIGNED_TOLERANCE,
    CompensationResult,
    CorrectionRule,
    Employee,
    IncrementRule,
    SalaryBand,
    SalaryPosition,
    iso_date,
)
from app.parsing import is_valid_rating, normalize_grade, normalize_key


def classify_salary_position(
    current: float,
    minimum: float,
    median: float,
    maximum: float,
    tolerance: float = MARKET_ALIGNED_TOLERANCE,
) -> SalaryPosition:
    if current < minimum:
        return SalaryPosition.BELOW_MINIMUM
    if current > maximum:
        return SalaryPosition.ABOVE_BAND
    if median > 0 and abs(current - median) / median <= tolerance:
        return SalaryPosition.MARKET_ALIGNED
    if current < median:
        return SalaryPosition.BELOW_MEDIAN
    if current > median:
        return SalaryPosition.ABOVE_MEDIAN
    return SalaryPosition.MARKET_ALIGNED


def band_lookup_key(department: str, grade: str, years_at_level: float | None) -> tuple:
    years = None if years_at_level is None else float(years_at_level)
    return (normalize_key(department), normalize_grade(grade), years)


def build_band_index(bands: list[SalaryBand]) -> dict[tuple, SalaryBand]:
    index: dict[tuple, SalaryBand] = {}
    for band in bands:
        key = band_lookup_key(band.department, band.grade, band.years_at_level)
        if key not in index:
            index[key] = band
    return index


def find_salary_band(
    employee: Employee,
    bands: list[SalaryBand],
    index: dict[tuple, SalaryBand] | None = None,
) -> SalaryBand | None:
    """Match Department + Grade + Years At Level. Same trio always yields the same band."""
    lookup = index if index is not None else build_band_index(bands)
    dept = normalize_key(employee.department)
    grade = normalize_grade(employee.grade)
    years = employee.years_at_level

    if years is not None:
        exact = lookup.get(band_lookup_key(employee.department, employee.grade, float(years)))
        if exact:
            return exact
        rounded = lookup.get(band_lookup_key(employee.department, employee.grade, float(int(years))))
        if rounded:
            return rounded

    candidates = [
        band
        for band in bands
        if normalize_key(band.department) == dept and normalize_grade(band.grade) == grade
    ]
    if not candidates:
        candidates = [band for band in bands if normalize_grade(band.grade) == grade]
    if not candidates and years is not None:
        candidates = [band for band in bands if band.years_at_level == years]
    if not candidates:
        return None
    if years is None:
        return min(candidates, key=lambda band: (band.years_at_level, band.min_salary))
    below_or_equal = [band for band in candidates if band.years_at_level <= years]
    if below_or_equal:
        return max(below_or_equal, key=lambda band: (band.years_at_level, -band.min_salary))
    return min(candidates, key=lambda band: (abs(band.years_at_level - years), band.years_at_level))


def find_increment(
    employee: Employee,
    rules: list[IncrementRule],
) -> IncrementRule | None:
    if not is_valid_rating(employee.performance_rating):
        return None
    grade = normalize_grade(employee.grade)
    rating = employee.performance_rating
    for rule in rules:
        if normalize_grade(rule.grade) == grade and rule.performance_rating == rating:
            return rule
    for rule in rules:
        if rule.performance_rating == rating:
            return rule
    return None


def find_correction(
    compa_ratio: float | None,
    rules: list[CorrectionRule],
) -> CorrectionRule | None:
    if compa_ratio is None:
        return None
    ordered = sorted(rules, key=lambda rule: (rule.min_compa, rule.max_compa))
    for rule in ordered:
        if rule.min_compa <= compa_ratio < rule.max_compa:
            return rule
    return None


def _below_min_correction(
    current: float,
    band_min: float,
    rules: list[CorrectionRule],
    looked_up: float,
) -> float:
    if looked_up > 0:
        return looked_up
    positive = [rule.correction_pct for rule in rules if rule.correction_pct > 0]
    if positive:
        return max(positive)
    if current > 0 and band_min > current:
        return round((band_min - current) / current, 6)
    return 0.0


def determine_correction(
    position: SalaryPosition,
    current: float,
    band_min: float | None,
    compa_ratio: float | None,
    rules: list[CorrectionRule],
) -> tuple[float, str | None]:
    if position == SalaryPosition.ABOVE_BAND:
        return 0.0, "Above maximum - salary correction withheld; performance increment only"

    looked_up = 0.0
    rule = find_correction(compa_ratio, rules)
    if rule is not None:
        looked_up = rule.correction_pct

    if position == SalaryPosition.BELOW_MINIMUM and band_min is not None:
        correction = _below_min_correction(current, band_min, rules, looked_up)
        return correction, "Below minimum - salary correction applied regardless of rating"

    if rule is None and compa_ratio is not None:
        return 0.0, "Correction rule not found - correction treated as 0%"
    return looked_up, None


def recommend_employee(
    employee: Employee,
    bands: list[SalaryBand],
    increment_rules: list[IncrementRule],
    correction_rules: list[CorrectionRule],
    band_index: dict[tuple, SalaryBand] | None = None,
) -> CompensationResult:
    flags: list[str] = []
    band = find_salary_band(employee, bands, band_index)

    band_min = band.min_salary if band else None
    band_median = band.median_salary if band else None
    band_max = band.max_salary if band else None
    band_years = band.years_at_level if band else None

    compa_ratio = None
    position = SalaryPosition.UNKNOWN
    if band is None:
        flags.append("Salary band not found - correction skipped")
    else:
        if band.median_salary <= 0:
            flags.append("Median salary is missing or zero - compa ratio skipped")
        else:
            compa_ratio = round(employee.current_salary / band.median_salary, 4)
        position = classify_salary_position(
            employee.current_salary,
            band.min_salary,
            band.median_salary,
            band.max_salary,
        )

    increment_rule = find_increment(employee, increment_rules)
    if increment_rule is None:
        increment_pct = 0.0
        flags.append("Increment rule not found - increment treated as 0%")
    else:
        increment_pct = increment_rule.increment_pct

    if band is None:
        correction_pct = 0.0
    else:
        correction_pct, correction_flag = determine_correction(
            position,
            employee.current_salary,
            band_min,
            compa_ratio,
            correction_rules,
        )
        if correction_flag:
            flags.append(correction_flag)

    total_increase_pct = round(increment_pct + correction_pct, 6)
    increment_amount = round(employee.current_salary * increment_pct, 4)
    correction_amount = round(employee.current_salary * correction_pct, 4)
    recommended_salary = round(employee.current_salary * (1 + total_increase_pct), 4)
    increase_amount = round(increment_amount + correction_amount, 4)

    if band_max is not None and recommended_salary > band_max:
        flags.append("Recommended salary exceeds band maximum")
    if employee.employment_status and normalize_key(employee.employment_status) not in {
        "active",
        "",
    }:
        flags.append(f"Employment status: {employee.employment_status}")
    if employee.performance_rating is not None and employee.performance_rating >= 4:
        if position in {SalaryPosition.BELOW_MINIMUM, SalaryPosition.BELOW_MEDIAN}:
            flags.append("High performer below market - priority correction")

    return CompensationResult(
        employee_id=employee.employee_id,
        employee_name=employee.employee_name,
        department=employee.department,
        grade=employee.grade,
        designation=employee.designation,
        location=employee.location,
        reporting_manager=employee.reporting_manager,
        reporting_partner=employee.reporting_partner,
        employment_status=employee.employment_status or "Active",
        date_of_joining=iso_date(employee.date_of_joining),
        current_grade_since=iso_date(employee.current_grade_since),
        years_at_level=employee.years_at_level,
        total_years_experience=employee.total_years_experience,
        performance_rating=employee.performance_rating,
        current_salary=round(employee.current_salary, 4),
        band_min=band_min,
        band_median=band_median,
        band_max=band_max,
        band_years_matched=band_years,
        compa_ratio=compa_ratio,
        salary_position=position.value,
        increment_pct=increment_pct,
        correction_pct=correction_pct,
        total_increase_pct=total_increase_pct,
        recommended_salary=recommended_salary,
        increase_amount=increase_amount,
        increment_amount=increment_amount,
        correction_amount=correction_amount,
        flags=flags,
    )


def recommend_all(
    employees: list[Employee],
    bands: list[SalaryBand],
    increment_rules: list[IncrementRule],
    correction_rules: list[CorrectionRule],
) -> list[CompensationResult]:
    index = build_band_index(bands)
    return [
        recommend_employee(employee, bands, increment_rules, correction_rules, index)
        for employee in employees
    ]


def filter_reports(
    reports: list[CompensationResult],
    employee_ids: list[str] | None = None,
    department: str | None = None,
    grade: str | None = None,
    position: str | None = None,
    status: str | None = None,
) -> list[CompensationResult]:
    selected = reports
    if employee_ids:
        wanted = {normalize_key(item) for item in employee_ids if str(item).strip()}
        selected = [row for row in selected if normalize_key(row.employee_id) in wanted]
    if department:
        key = normalize_key(department)
        selected = [row for row in selected if normalize_key(row.department) == key]
    if grade:
        key = normalize_grade(grade)
        selected = [row for row in selected if normalize_grade(row.grade) == key]
    if position:
        key = normalize_key(position)
        selected = [row for row in selected if normalize_key(row.salary_position) == key]
    if status:
        key = normalize_key(status)
        selected = [row for row in selected if normalize_key(row.employment_status) == key]
    return selected


def missing_ids(reports: list[CompensationResult], employee_ids: list[str]) -> list[str]:
    found = {normalize_key(row.employee_id) for row in reports}
    missing: list[str] = []
    seen: set[str] = set()
    for raw in employee_ids:
        text = str(raw).strip()
        if not text:
            continue
        key = normalize_key(text)
        if key in seen:
            continue
        seen.add(key)
        if key not in found:
            missing.append(text)
    return missing
