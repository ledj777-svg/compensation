from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from typing import Any

from app.models import ValidationIssue

MISSING_EMPLOYEE_ID = "MISSING_EMPLOYEE_ID"
MISSING_SALARY = "MISSING_SALARY"
MISSING_GRADE = "MISSING_GRADE"
INVALID_RATING = "INVALID_RATING"
DUPLICATE_RECORD = "DUPLICATE_RECORD"
INCOMPLETE_RULE = "INCOMPLETE_RULE"


def issue(
    sheet: str,
    row: int | None,
    code: str,
    message: str,
    employee_id: str | None = None,
    severity: str = "error",
) -> ValidationIssue:
    return ValidationIssue(
        sheet=sheet,
        row=row,
        employee_id=employee_id,
        code=code,
        severity=severity,
        message=message,
    )


def summarize_issues(issues: list[ValidationIssue]) -> dict[str, Any]:
    by_code = Counter(item.code for item in issues)
    errors = [item for item in issues if item.severity == "error"]
    warnings = [item for item in issues if item.severity != "error"]
    return {
        "error_count": len(errors),
        "warning_count": len(warnings),
        "issue_count": len(issues),
        "by_code": dict(by_code),
        "issues": [asdict(item) for item in issues],
    }
