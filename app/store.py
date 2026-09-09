from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock

from app.defaults import apply_defaults, ensure_coverage
from app.engine import recommend_all
from app.ingest import read_workbook
from app.models import Dataset
from app.validation import summarize_issues


class EmptyStoreError(RuntimeError):
    pass


class DatasetStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._dataset: Dataset | None = None
        self._awaiting_formulas = False

    def load(self, filename: str, payload: bytes) -> Dataset:
        employees, increment_rules, salary_bands, correction_rules, issues, counts = read_workbook(payload)
        counts = dict(counts)
        with self._lock:
            existing = self._dataset
            awaiting = self._awaiting_formulas
        new_has_employees = bool(employees)
        new_has_rules = bool(increment_rules or salary_bands or correction_rules)
        if existing and awaiting and not new_has_employees:
            employees = existing.employees
            issues = list(existing.issues) + list(issues)
            counts["found_fields"] = existing.sheet_counts.get("found_fields") or counts.get("found_fields") or []
            counts["Employee_Master"] = len(employees)
            if not increment_rules:
                increment_rules = existing.increment_rules
            if not salary_bands:
                salary_bands = existing.salary_bands
            if not correction_rules:
                correction_rules = existing.correction_rules
        elif existing and awaiting and new_has_employees and new_has_rules:
            if not increment_rules:
                increment_rules = existing.increment_rules
            if not salary_bands:
                salary_bands = existing.salary_bands
            if not correction_rules:
                correction_rules = existing.correction_rules
        missing = [
            name
            for name, present in (
                ("Increment_Grid", bool(increment_rules)),
                ("Salary_Band", bool(salary_bands)),
                ("Salary_Correction_Rules", bool(correction_rules)),
            )
            if not present
        ]
        counts["missing_sheets"] = missing
        counts["complete"] = not missing
        counts["used_defaults"] = []
        awaiting = bool(missing)
        if awaiting:
            reports = []
        else:
            increment_rules, salary_bands, correction_rules = ensure_coverage(
                employees, increment_rules, salary_bands, correction_rules
            )
            reports = recommend_all(employees, salary_bands, increment_rules, correction_rules)
        dataset = Dataset(
            source_filename=filename,
            uploaded_at=datetime.now(timezone.utc),
            employees=employees,
            increment_rules=increment_rules,
            salary_bands=salary_bands,
            correction_rules=correction_rules,
            reports=reports,
            issues=issues,
            sheet_counts=counts,
        )
        with self._lock:
            self._dataset = dataset
            self._awaiting_formulas = awaiting
        return dataset

    def use_defaults(self) -> Dataset:
        with self._lock:
            if self._dataset is None:
                raise EmptyStoreError("Upload an Excel workbook before generating reports.")
            dataset = self._dataset
        increment_rules, salary_bands, correction_rules, used = apply_defaults(
            dataset.employees,
            dataset.increment_rules,
            dataset.salary_bands,
            dataset.correction_rules,
        )
        increment_rules, salary_bands, correction_rules = ensure_coverage(
            dataset.employees, increment_rules, salary_bands, correction_rules
        )
        counts = dict(dataset.sheet_counts)
        counts["used_defaults"] = used
        counts["missing_sheets"] = []
        counts["complete"] = True
        reports = recommend_all(
            dataset.employees, salary_bands, increment_rules, correction_rules
        )
        updated = Dataset(
            source_filename=dataset.source_filename,
            uploaded_at=dataset.uploaded_at,
            employees=dataset.employees,
            increment_rules=increment_rules,
            salary_bands=salary_bands,
            correction_rules=correction_rules,
            reports=reports,
            issues=dataset.issues,
            sheet_counts=counts,
        )
        with self._lock:
            self._dataset = updated
            self._awaiting_formulas = False
        return updated

    def get(self) -> Dataset:
        with self._lock:
            if self._dataset is None:
                raise EmptyStoreError("Upload an Excel workbook before generating reports.")
            return self._dataset

    def summary(self) -> dict | None:
        with self._lock:
            dataset = self._dataset
            if dataset is None:
                return None
            return {
                "source_filename": dataset.source_filename,
                "uploaded_at": dataset.uploaded_at.isoformat(),
                "sheet_counts": {
                    key: value
                    for key, value in dataset.sheet_counts.items()
                    if key
                    not in {"missing_sheets", "found_fields", "complete", "used_defaults"}
                },
                "missing_sheets": dataset.sheet_counts.get("missing_sheets") or [],
                "found_fields": dataset.sheet_counts.get("found_fields") or [],
                "used_defaults": dataset.sheet_counts.get("used_defaults") or [],
                "complete": bool(dataset.sheet_counts.get("complete")),
                "awaiting_formulas": self._awaiting_formulas,
                "employee_count": len(dataset.employees),
                "report_count": len(dataset.reports),
                "warning_count": summarize_issues(dataset.issues)["warning_count"],
                "error_count": summarize_issues(dataset.issues)["error_count"],
                "validation": summarize_issues(dataset.issues),
                "warnings": [
                    {
                        "sheet": item.sheet,
                        "row": item.row,
                        "employee_id": item.employee_id,
                        "code": item.code,
                        "severity": item.severity,
                        "message": item.message,
                    }
                    for item in dataset.issues
                ],
            }


store = DatasetStore()
