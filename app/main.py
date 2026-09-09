from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.budget import build_budget
from app.compare import build_comparison
from app.engine import filter_reports, missing_ids
from app.export import (
    build_comparison_workbook,
    build_compensation_workbook,
    build_selected_workbook,
    build_validation_workbook,
)
from app.validation import summarize_issues
from app.ingest import IngestError
from app.store import EmptyStoreError, store

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI(
    title="Compensation Planning Platform",
    description="Phase 1 rule-based salary recommendation engine.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class EmployeeIdsRequest(BaseModel):
    employee_ids: list[str] = Field(default_factory=list)


def _parse_ids(raw_ids: list[str] | None, fallback: str | None = None) -> list[str]:
    collected: list[str] = []
    sources = list(raw_ids or [])
    if fallback:
        sources.append(fallback)
    for item in sources:
        for token in str(item).replace(";", ",").replace("\n", ",").split(","):
            token = token.strip()
            if token:
                collected.append(token)
    # Preserve order, drop duplicates.
    unique: list[str] = []
    seen: set[str] = set()
    for item in collected:
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _require_dataset():
    try:
        return store.get()
    except EmptyStoreError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "phase": 1}


@app.get("/api/status")
def status() -> dict:
    summary = store.summary()
    return {"loaded": summary is not None, "dataset": summary}


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)) -> dict:
    filename = file.filename or "workbook.xlsx"
    if not filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="Upload an .xlsx Excel workbook.")
    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    try:
        dataset = store.load(filename, payload)
    except IngestError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    summary = store.summary()
    return {
        "ok": True,
        "dataset": summary,
        "validation": summarize_issues(dataset.issues),
        "preview": [row.to_dict() for row in dataset.reports[:8]],
        "awaiting_formulas": bool(summary and summary.get("awaiting_formulas")),
    }


@app.post("/api/use-defaults")
def use_defaults() -> dict:
    try:
        dataset = store.use_defaults()
    except EmptyStoreError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "ok": True,
        "dataset": store.summary(),
        "preview": [row.to_dict() for row in dataset.reports[:8]],
    }


@app.get("/api/reports")
def reports(
    department: str | None = None,
    grade: str | None = None,
    position: str | None = None,
    status: str | None = None,
    q: str | None = Query(default=None, description="Search name or employee ID"),
) -> dict:
    dataset = _require_dataset()
    rows = filter_reports(
        dataset.reports,
        department=department,
        grade=grade,
        position=position,
        status=status,
    )
    if q:
        needle = q.strip().casefold()
        rows = [
            row
            for row in rows
            if needle in row.employee_id.casefold() or needle in row.employee_name.casefold()
        ]
    departments = sorted({row.department for row in dataset.reports if row.department})
    grades = sorted({row.grade for row in dataset.reports if row.grade})
    positions = sorted({row.salary_position for row in dataset.reports})
    statuses = sorted({row.employment_status for row in dataset.reports if row.employment_status})
    return {
        "source_filename": dataset.source_filename,
        "count": len(rows),
        "filters": {
            "departments": departments,
            "grades": grades,
            "positions": positions,
            "statuses": statuses,
        },
        "reports": [row.to_dict() for row in rows],
    }


@app.post("/api/reports/selected")
def selected_reports(payload: EmployeeIdsRequest) -> dict:
    dataset = _require_dataset()
    ids = _parse_ids(payload.employee_ids)
    if not ids:
        raise HTTPException(status_code=400, detail="Enter at least one employee ID.")
    rows = filter_reports(dataset.reports, employee_ids=ids)
    return {
        "count": len(rows),
        "missing_ids": missing_ids(dataset.reports, ids),
        "reports": [row.to_dict() for row in rows],
    }


@app.post("/api/compare")
def compare(payload: EmployeeIdsRequest) -> dict:
    dataset = _require_dataset()
    ids = _parse_ids(payload.employee_ids)
    if len(ids) < 2:
        raise HTTPException(status_code=400, detail="Enter at least two employee IDs to compare.")
    ordered = []
    found_keys = {row.employee_id.casefold(): row for row in dataset.reports}
    for employee_id in ids:
        match = found_keys.get(employee_id.casefold())
        if match:
            ordered.append(match)
    missing = missing_ids(dataset.reports, ids)
    if len(ordered) < 2:
        raise HTTPException(
            status_code=404,
            detail="Need at least two matching employee IDs. Missing: " + ", ".join(missing or ids),
        )
    comparison = build_comparison(ordered)
    comparison["missing_ids"] = missing
    comparison["requested_ids"] = ids
    return comparison


@app.get("/api/budget")
def budget() -> dict:
    dataset = _require_dataset()
    return build_budget(dataset.reports)


@app.get("/api/validation")
def validation() -> dict:
    dataset = _require_dataset()
    return summarize_issues(dataset.issues)


def _xlsx_response(content: bytes, filename: str) -> Response:
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/export/compensation")
def export_compensation() -> Response:
    dataset = _require_dataset()
    budget_data = build_budget(dataset.reports)
    content = build_compensation_workbook(dataset.reports, budget_data, dataset.issues)
    return _xlsx_response(content, "compensation_report.xlsx")


@app.post("/api/export/selected")
def export_selected(payload: EmployeeIdsRequest) -> Response:
    dataset = _require_dataset()
    ids = _parse_ids(payload.employee_ids)
    if not ids:
        raise HTTPException(status_code=400, detail="Enter at least one employee ID.")
    rows = filter_reports(dataset.reports, employee_ids=ids)
    if not rows:
        raise HTTPException(status_code=404, detail="No matching employees were found.")
    return _xlsx_response(build_selected_workbook(rows), "selected_employees_report.xlsx")


@app.post("/api/export/comparison")
def export_comparison(payload: EmployeeIdsRequest) -> Response:
    dataset = _require_dataset()
    ids = _parse_ids(payload.employee_ids)
    ordered = []
    found_keys = {row.employee_id.casefold(): row for row in dataset.reports}
    for employee_id in ids:
        match = found_keys.get(employee_id.casefold())
        if match:
            ordered.append(match)
    if len(ordered) < 2:
        raise HTTPException(status_code=400, detail="Enter at least two matching employee IDs.")
    return _xlsx_response(build_comparison_workbook(ordered), "employee_comparison.xlsx")


@app.get("/api/export/budget")
def export_budget() -> Response:
    dataset = _require_dataset()
    budget_data = build_budget(dataset.reports)
    content = build_compensation_workbook(dataset.reports, budget_data, dataset.issues)
    return _xlsx_response(content, "budget_analysis.xlsx")


@app.get("/api/export/validation")
def export_validation() -> Response:
    dataset = _require_dataset()
    return _xlsx_response(build_validation_workbook(dataset.issues), "validation_report.xlsx")


if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
