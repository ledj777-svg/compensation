from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from enum import Enum
from typing import Any


MARKET_ALIGNED_TOLERANCE = 0.03


class SalaryPosition(str, Enum):
    BELOW_MINIMUM = "Below Minimum"
    BELOW_MEDIAN = "Below Median"
    MARKET_ALIGNED = "Market Aligned"
    ABOVE_MEDIAN = "Above Median"
    ABOVE_BAND = "Above Band"
    UNKNOWN = "Unknown"


@dataclass
class Employee:
    employee_id: str
    employee_name: str
    department: str
    grade: str
    designation: str
    current_salary: float
    performance_rating: int | None
    date_of_joining: date | None
    current_grade_since: date | None
    years_at_level: float | None
    total_years_experience: float | None
    location: str
    reporting_manager: str
    reporting_partner: str
    employment_status: str
    row_number: int = 0


@dataclass
class IncrementRule:
    grade: str
    performance_rating: int
    increment_pct: float


@dataclass
class SalaryBand:
    department: str
    grade: str
    years_at_level: float
    min_salary: float
    median_salary: float
    max_salary: float
    raw_years_label: str = ""


@dataclass
class CorrectionRule:
    min_compa: float
    max_compa: float
    correction_pct: float


@dataclass
class CompensationResult:
    employee_id: str
    employee_name: str
    department: str
    grade: str
    designation: str
    location: str
    reporting_manager: str
    reporting_partner: str
    employment_status: str
    date_of_joining: str | None
    current_grade_since: str | None
    years_at_level: float | None
    total_years_experience: float | None
    performance_rating: int | None
    current_salary: float
    band_min: float | None
    band_median: float | None
    band_max: float | None
    band_years_matched: float | None
    compa_ratio: float | None
    salary_position: str
    increment_pct: float
    correction_pct: float
    total_increase_pct: float
    recommended_salary: float
    increase_amount: float
    increment_amount: float = 0.0
    correction_amount: float = 0.0
    flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ValidationIssue:
    sheet: str
    row: int | None
    employee_id: str | None
    code: str
    severity: str
    message: str


# Back-compat alias used by older call sites.
IngestWarning = ValidationIssue


@dataclass
class Dataset:
    source_filename: str
    uploaded_at: datetime
    employees: list[Employee]
    increment_rules: list[IncrementRule]
    salary_bands: list[SalaryBand]
    correction_rules: list[CorrectionRule]
    reports: list[CompensationResult]
    issues: list[ValidationIssue]
    sheet_counts: dict[str, int]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return self.issues


def iso_date(value: date | None) -> str | None:
    return value.isoformat() if value else None
