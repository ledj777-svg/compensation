from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.sample_workbook import build_sample_workbook
from app.store import store


client = TestClient(app)


def setup_function() -> None:
    store._dataset = None
    store._awaiting_formulas = False


def test_upload_and_spec_example_via_api():
    files = {
        "file": (
            "sample.xlsx",
            build_sample_workbook(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    upload = client.post("/api/upload", files=files)
    assert upload.status_code == 200, upload.text
    body = upload.json()
    assert body["dataset"]["sheet_counts"]["Employee_Master"] == 28

    reports = client.get("/api/reports").json()["reports"]
    ananya = next(row for row in reports if row["employee_id"] == "1001")
    assert ananya["increment_pct"] == 0.10
    assert ananya["correction_pct"] == 0.08
    assert ananya["recommended_salary"] == 11.8
    assert body["dataset"]["awaiting_formulas"] is False

    selected = client.post("/api/reports/selected", json={"employee_ids": ["1001", "1002"]})
    assert selected.status_code == 200
    assert selected.json()["count"] == 2

    comparison = client.post("/api/compare", json={"employee_ids": ["1001\n1002"]})
    assert comparison.status_code == 200
    payload = comparison.json()
    assert len(payload["employees"]) == 2
    current = next(metric for metric in payload["metrics"] if metric["key"] == "current_salary")
    assert current["values"] == [10, 14]

    budget = client.get("/api/budget")
    assert budget.status_code == 200
    payload_budget = budget.json()
    assert payload_budget["headcount"] >= 1
    assert "increment_cost" in payload_budget
    assert "correction_cost" in payload_budget
    assert "total_compensation_cost" in payload_budget
    assert payload_budget["total_compensation_cost"] == round(
        payload_budget["increment_cost"] + payload_budget["correction_cost"], 4
    )

    validation = client.get("/api/validation")
    assert validation.status_code == 200
    assert validation.json()["error_count"] == 0

    export = client.get("/api/export/compensation")
    assert export.status_code == 200
    assert export.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert len(export.content) > 1000

    validation_xlsx = client.get("/api/export/validation")
    assert validation_xlsx.status_code == 200


def test_employee_only_waits_then_uses_defaults():
    from io import BytesIO

    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(
        [
            "Employee ID",
            "Employee Name",
            "Department",
            "Grade",
            "Designation",
            "Current Salary",
            "Performance Rating",
            "Years At Level",
        ]
    )
    sheet.append([1001, "Ananya Rao", "Technology", "A1", "Software Engineer", 10, 4, 2])
    buffer = BytesIO()
    workbook.save(buffer)
    upload = client.post(
        "/api/upload",
        files={
            "file": (
                "employees.xlsx",
                buffer.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert upload.status_code == 200, upload.text
    assert upload.json()["dataset"]["awaiting_formulas"] is True
    assert upload.json()["dataset"]["report_count"] == 0

    applied = client.post("/api/use-defaults")
    assert applied.status_code == 200
    assert applied.json()["dataset"]["awaiting_formulas"] is False
    reports = client.get("/api/reports").json()["reports"]
    ananya = next(row for row in reports if row["employee_id"] == "1001")
    assert ananya["recommended_salary"] == 11.8
