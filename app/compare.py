from __future__ import annotations

from typing import Any

from app.models import CompensationResult

COMPARISON_METRICS = [
    ("employee_id", "Employee ID", "text"),
    ("employee_name", "Employee Name", "text"),
    ("department", "Department", "text"),
    ("grade", "Grade", "text"),
    ("current_salary", "Current Salary", "money"),
    ("performance_rating", "Performance Rating", "number"),
    ("years_at_level", "Years At Level", "number"),
    ("band_min", "Minimum Salary", "money"),
    ("band_median", "Median Salary", "money"),
    ("band_max", "Maximum Salary", "money"),
    ("salary_position", "Salary Position", "text"),
    ("compa_ratio", "Compa Ratio", "ratio"),
    ("increment_pct", "Increment %", "percent"),
    ("correction_pct", "Salary Correction %", "percent"),
    ("total_increase_pct", "Total Increase %", "percent"),
    ("recommended_salary", "Recommended Salary", "money"),
]


def _extremes(values: list[Any]) -> dict[str, Any]:
    numeric = [value for value in values if isinstance(value, (int, float))]
    if not numeric:
        return {"min": None, "max": None, "spread": None}
    lowest = min(numeric)
    highest = max(numeric)
    return {
        "min": lowest,
        "max": highest,
        "spread": round(highest - lowest, 6),
    }


def build_comparison(reports: list[CompensationResult]) -> dict[str, Any]:
    metrics = []
    for key, label, kind in COMPARISON_METRICS:
        values = [getattr(row, key) for row in reports]
        entry = {
            "key": key,
            "label": label,
            "kind": kind,
            "values": values,
        }
        if kind in {"money", "number", "percent", "ratio"}:
            entry.update(_extremes(values))
        metrics.append(entry)

    return {
        "employees": [row.to_dict() for row in reports],
        "metrics": metrics,
    }
