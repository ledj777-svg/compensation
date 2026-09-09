from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.models import CompensationResult
from app.parsing import normalize_key


ACTIVE_STATUSES = {"active", ""}


def _is_active(row: CompensationResult) -> bool:
    return normalize_key(row.employment_status) in ACTIVE_STATUSES


def _group_rows(rows: list[CompensationResult], key_fn) -> list[dict[str, Any]]:
    buckets: dict[str, list[CompensationResult]] = defaultdict(list)
    for row in rows:
        buckets[key_fn(row)].append(row)
    grouped = []
    for label, items in sorted(buckets.items(), key=lambda pair: pair[0]):
        current = sum(item.current_salary for item in items)
        recommended = sum(item.recommended_salary for item in items)
        increment_cost = sum(item.increment_amount for item in items)
        correction_cost = sum(item.correction_amount for item in items)
        increase = increment_cost + correction_cost
        grouped.append(
            {
                "label": label,
                "headcount": len(items),
                "current_payroll": round(current, 4),
                "recommended_payroll": round(recommended, 4),
                "increment_cost": round(increment_cost, 4),
                "correction_cost": round(correction_cost, 4),
                "total_compensation_cost": round(increase, 4),
                "increase_amount": round(increase, 4),
                "increase_pct": round(increase / current, 6) if current else 0.0,
                "avg_increment_pct": round(
                    sum(item.increment_pct for item in items) / len(items), 6
                ),
                "avg_correction_pct": round(
                    sum(item.correction_pct for item in items) / len(items), 6
                ),
                "avg_compa_ratio": round(
                    sum(item.compa_ratio for item in items if item.compa_ratio is not None)
                    / max(1, sum(1 for item in items if item.compa_ratio is not None)),
                    4,
                )
                if any(item.compa_ratio is not None for item in items)
                else None,
            }
        )
    return grouped


def build_budget(reports: list[CompensationResult]) -> dict[str, Any]:
    active = [row for row in reports if _is_active(row)]
    population = active if active else reports
    current = sum(row.current_salary for row in population)
    recommended = sum(row.recommended_salary for row in population)
    increment_cost = sum(row.increment_amount for row in population)
    correction_cost = sum(row.correction_amount for row in population)
    total_cost = increment_cost + correction_cost

    positions: dict[str, int] = defaultdict(int)
    for row in population:
        positions[row.salary_position] += 1

    priority = [
        row.to_dict()
        for row in population
        if "High performer below market - priority correction" in row.flags
    ]
    below_min = [row.to_dict() for row in population if row.salary_position == "Below Minimum"]
    above_band = [row.to_dict() for row in population if row.salary_position == "Above Band"]

    return {
        "scope": "Active employees" if active else "All employees",
        "headcount": len(population),
        "excluded_inactive": len(reports) - len(population),
        "current_payroll": round(current, 4),
        "recommended_payroll": round(recommended, 4),
        "increment_cost": round(increment_cost, 4),
        "correction_cost": round(correction_cost, 4),
        "total_compensation_cost": round(total_cost, 4),
        "increase_amount": round(total_cost, 4),
        "increase_pct": round(total_cost / current, 6) if current else 0.0,
        "avg_increment_pct": round(
            sum(row.increment_pct for row in population) / len(population), 6
        )
        if population
        else 0.0,
        "avg_correction_pct": round(
            sum(row.correction_pct for row in population) / len(population), 6
        )
        if population
        else 0.0,
        "avg_total_increase_pct": round(
            sum(row.total_increase_pct for row in population) / len(population), 6
        )
        if population
        else 0.0,
        "avg_compa_ratio": round(
            sum(row.compa_ratio for row in population if row.compa_ratio is not None)
            / max(1, sum(1 for row in population if row.compa_ratio is not None)),
            4,
        )
        if any(row.compa_ratio is not None for row in population)
        else None,
        "employees_with_correction": sum(1 for row in population if row.correction_pct > 0),
        "employees_below_minimum": len(below_min),
        "employees_above_band": len(above_band),
        "priority_cases": len(priority),
        "position_mix": dict(positions),
        "by_department": _group_rows(population, lambda row: row.department or "Unspecified"),
        "by_grade": _group_rows(population, lambda row: row.grade or "Unspecified"),
        "by_rating": _group_rows(
            population,
            lambda row: str(row.performance_rating)
            if row.performance_rating is not None
            else "Unrated",
        ),
        "by_position": _group_rows(population, lambda row: row.salary_position),
        "priority_employees": priority,
        "below_minimum_employees": below_min,
        "above_band_employees": above_band,
    }
