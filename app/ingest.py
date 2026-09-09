from __future__ import annotations

from io import BytesIO
from typing import Any

import pandas as pd

from app.models import CorrectionRule, Employee, IncrementRule, SalaryBand, ValidationIssue
from app.parsing import (
    cell_text,
    first_number,
    is_valid_rating,
    normalize_header,
    parse_date,
    parse_percent,
    parse_rating,
    parse_salary_lpa,
    parse_years,
)
from app.validation import (
    DUPLICATE_RECORD,
    INCOMPLETE_RULE,
    INVALID_RATING,
    MISSING_EMPLOYEE_ID,
    MISSING_GRADE,
    MISSING_SALARY,
    issue,
)

SHEET_ALIASES = {
    "sheet1": "Employee_Master",
    "sheet 1": "Employee_Master",
    "employeemaster": "Employee_Master",
    "employees": "Employee_Master",
    "employee": "Employee_Master",
    "incrementgrid": "Increment_Grid",
    "increment": "Increment_Grid",
    "increments": "Increment_Grid",
    "salaryband": "Salary_Band",
    "salarybands": "Salary_Band",
    "bands": "Salary_Band",
    "salarycorrectionrules": "Salary_Correction_Rules",
    "correctionrules": "Salary_Correction_Rules",
    "corrections": "Salary_Correction_Rules",
    "salarycorrection": "Salary_Correction_Rules",
}

EMPLOYEE_COLUMNS = {
    "employeeid": "employee_id",
    "empid": "employee_id",
    "id": "employee_id",
    "employeename": "employee_name",
    "name": "employee_name",
    "department": "department",
    "dept": "department",
    "grade": "grade",
    "designation": "designation",
    "title": "designation",
    "currentsalary": "current_salary",
    "salary": "current_salary",
    "ctc": "current_salary",
    "currentctc": "current_salary",
    "performancerating": "performance_rating",
    "rating": "performance_rating",
    "lastrating": "performance_rating",
    "dateofjoining": "date_of_joining",
    "doj": "date_of_joining",
    "currentgradesince": "current_grade_since",
    "gradesince": "current_grade_since",
    "yearsatlevel": "years_at_level",
    "yearsinlevel": "years_at_level",
    "yearsingrade": "years_at_level",
    "yal": "years_at_level",
    "totalyearsexperience": "total_years_experience",
    "experience": "total_years_experience",
    "totalexperience": "total_years_experience",
    "location": "location",
    "reportingmanager": "reporting_manager",
    "manager": "reporting_manager",
    "reportingpartner": "reporting_partner",
    "partner": "reporting_partner",
    "employmentstatus": "employment_status",
    "status": "employment_status",
}

INCREMENT_COLUMNS = {
    "grade": "grade",
    "performancerating": "performance_rating",
    "rating": "performance_rating",
    "incrementpercentage": "increment_pct",
    "incrementpercent": "increment_pct",
    "increment": "increment_pct",
    "incrementpct": "increment_pct",
}

BAND_COLUMNS = {
    "department": "department",
    "dept": "department",
    "grade": "grade",
    "yearsatlevel": "years_at_level",
    "years": "years_at_level",
    "minimumsalary": "min_salary",
    "minsalary": "min_salary",
    "min": "min_salary",
    "mediansalary": "median_salary",
    "median": "median_salary",
    "maximumsalary": "max_salary",
    "maxsalary": "max_salary",
    "max": "max_salary",
}

CORRECTION_COLUMNS = {
    "minimumcomparatio": "min_compa",
    "mincompa": "min_compa",
    "mincomparatio": "min_compa",
    "from": "min_compa",
    "maximumcomparatio": "max_compa",
    "maxcompa": "max_compa",
    "maxcomparatio": "max_compa",
    "to": "max_compa",
    "salarycorrection": "correction_pct",
    "correction": "correction_pct",
    "correctionpct": "correction_pct",
    "salarycorrectionpct": "correction_pct",
}


class IngestError(ValueError):
    pass


def _canonical_sheet_name(name: str) -> str | None:
    return SHEET_ALIASES.get(normalize_header(name))


def _rename_columns(frame: pd.DataFrame, mapping: dict[str, str]) -> pd.DataFrame:
    cleaned = frame.copy()
    cleaned.columns = [str(column).replace("\n", " ").replace("\r", " ").strip() for column in cleaned.columns]
    rename: dict[str, str] = {}
    used: set[str] = set()
    for column in cleaned.columns:
        field = mapping.get(normalize_header(column))
        if field and field not in used:
            rename[column] = field
            used.add(field)
    return cleaned.rename(columns=rename)


def _require_columns(frame: pd.DataFrame, required: list[str], sheet: str) -> None:
    missing = [name for name in required if name not in frame.columns]
    if missing:
        raise IngestError(f"{sheet} is missing required columns: {', '.join(missing)}")


def _cell(row: pd.Series, field: str) -> Any:
    if field not in row.index:
        return None
    return row[field]


def _drop_empty(frame: pd.DataFrame) -> pd.DataFrame:
    cleaned = frame.dropna(how="all")
    if cleaned.empty:
        return cleaned
    stringy = cleaned.apply(
        lambda col: col.astype(str).str.strip().isin({"", "nan", "None", "<NA>"})
    )
    return cleaned.loc[~stringy.all(axis=1)].copy()


def read_workbook(data: bytes) -> tuple[
    list[Employee],
    list[IncrementRule],
    list[SalaryBand],
    list[CorrectionRule],
    list[ValidationIssue],
    dict[str, int],
]:
    try:
        workbook = pd.ExcelFile(BytesIO(data), engine="openpyxl")
    except Exception as exc:
        raise IngestError(f"Could not read Excel workbook: {exc}") from exc

    sheets: dict[str, str] = {}
    for name in workbook.sheet_names:
        canonical = _canonical_sheet_name(name)
        if canonical:
            sheets[canonical] = name

    if "Employee_Master" not in sheets:
        guessed = _guess_employee_sheet(workbook)
        if guessed:
            sheets["Employee_Master"] = guessed

    issues: list[ValidationIssue] = []
    if "Employee_Master" not in sheets:
        raise IngestError(
            "I could not find employee data. Add a sheet with Employee ID, Employee Name, "
            "Department, Grade, Current Salary, Performance Rating, and Years At Level."
        )

    employees, found_fields = _read_employees(
        _read_sheet_with_header(workbook, sheets["Employee_Master"]), issues
    )
    increment_rules = (
        _read_increments(pd.read_excel(workbook, sheets["Increment_Grid"], dtype=object), issues)
        if "Increment_Grid" in sheets
        else []
    )
    salary_bands = (
        _read_bands(pd.read_excel(workbook, sheets["Salary_Band"], dtype=object), issues)
        if "Salary_Band" in sheets
        else []
    )
    correction_rules = (
        _read_corrections(
            pd.read_excel(workbook, sheets["Salary_Correction_Rules"], dtype=object), issues
        )
        if "Salary_Correction_Rules" in sheets
        else []
    )
    missing_sheets = [
        name
        for name, present in (
            ("Increment_Grid", bool(increment_rules)),
            ("Salary_Band", bool(salary_bands)),
            ("Salary_Correction_Rules", bool(correction_rules)),
        )
        if not present
    ]
    counts = {
        "Employee_Master": len(employees),
        "Increment_Grid": len(increment_rules),
        "Salary_Band": len(salary_bands),
        "Salary_Correction_Rules": len(correction_rules),
        "missing_sheets": missing_sheets,
        "found_fields": found_fields,
        "complete": not missing_sheets,
    }
    return employees, increment_rules, salary_bands, correction_rules, issues, counts


def _read_sheet_with_header(workbook: pd.ExcelFile, name: str) -> pd.DataFrame:
    raw = pd.read_excel(workbook, name, dtype=object, header=None)
    if raw.empty:
        return raw
    header_row = 0
    for index in range(min(15, len(raw))):
        fields = _row_mapped_fields(list(raw.iloc[index].values))
        if "employee_id" in fields and "current_salary" in fields:
            header_row = index
            break
    frame = raw.iloc[header_row:].copy()
    frame.columns = frame.iloc[0]
    frame = frame.iloc[1:].reset_index(drop=True)
    return frame


FIELD_LABELS = {
    "employee_id": "Employee ID",
    "employee_name": "Employee Name",
    "department": "Department",
    "grade": "Grade",
    "designation": "Designation",
    "current_salary": "Current Salary",
    "performance_rating": "Performance Rating",
    "date_of_joining": "Date of Joining",
    "current_grade_since": "Current Grade Since",
    "years_at_level": "Years At Level",
    "total_years_experience": "Total Years Experience",
    "location": "Location",
    "reporting_manager": "Reporting Manager",
    "reporting_partner": "Reporting Partner",
    "employment_status": "Employment Status",
}


def _row_mapped_fields(values: list[Any]) -> set[str]:
    found: set[str] = set()
    for value in values:
        field = EMPLOYEE_COLUMNS.get(normalize_header(value))
        if field:
            found.add(field)
    return found


def _guess_employee_sheet(workbook: pd.ExcelFile) -> str | None:
    for name in workbook.sheet_names:
        raw = pd.read_excel(workbook, name, dtype=object, header=None)
        if raw.empty:
            continue
        limit = min(15, len(raw))
        for index in range(limit):
            fields = _row_mapped_fields(list(raw.iloc[index].values))
            if "employee_id" in fields and "current_salary" in fields:
                return name
        renamed = _rename_columns(raw, EMPLOYEE_COLUMNS)
        if "employee_id" in renamed.columns and "current_salary" in renamed.columns:
            return name
    if workbook.sheet_names:
        return workbook.sheet_names[0]
    return None


def _read_employees(frame: pd.DataFrame, issues: list[ValidationIssue]) -> tuple[list[Employee], list[str]]:
    frame = _rename_columns(_drop_empty(frame), EMPLOYEE_COLUMNS)
    _require_columns(frame, ["employee_id", "current_salary"], "Employee_Master")
    found_fields = [FIELD_LABELS[name] for name in FIELD_LABELS if name in frame.columns]
    employees: list[Employee] = []
    seen: dict[str, int] = {}
    for offset, row in frame.reset_index(drop=True).iterrows():
        excel_row = int(offset) + 2
        employee_id = cell_text(_cell(row, "employee_id"))
        grade = cell_text(_cell(row, "grade"))
        salary = parse_salary_lpa(_cell(row, "current_salary"))
        rating_raw = _cell(row, "performance_rating")
        rating = parse_rating(rating_raw)

        if not employee_id:
            issues.append(
                issue("Employee_Master", excel_row, MISSING_EMPLOYEE_ID, "Missing Employee ID")
            )
            continue
        if employee_id in seen:
            issues.append(
                issue(
                    "Employee_Master",
                    excel_row,
                    DUPLICATE_RECORD,
                    f"Duplicate Employee ID {employee_id} - first row {seen[employee_id]} kept",
                    employee_id=employee_id,
                )
            )
            continue
        if not grade:
            issues.append(
                issue(
                    "Employee_Master",
                    excel_row,
                    MISSING_GRADE,
                    f"{employee_id}: missing Grade",
                    employee_id=employee_id,
                )
            )
            continue
        if salary is None:
            issues.append(
                issue(
                    "Employee_Master",
                    excel_row,
                    MISSING_SALARY,
                    f"{employee_id}: missing Current Salary",
                    employee_id=employee_id,
                )
            )
            continue
        if not is_valid_rating(rating):
            issues.append(
                issue(
                    "Employee_Master",
                    excel_row,
                    INVALID_RATING,
                    f"{employee_id}: invalid Performance Rating {cell_text(rating_raw) or '(blank)'}",
                    employee_id=employee_id,
                )
            )
            rating = None

        seen[employee_id] = excel_row
        employees.append(
            Employee(
                employee_id=employee_id,
                employee_name=cell_text(_cell(row, "employee_name")),
                department=cell_text(_cell(row, "department")),
                grade=grade,
                designation=cell_text(_cell(row, "designation")),
                current_salary=salary,
                performance_rating=rating,
                date_of_joining=parse_date(_cell(row, "date_of_joining")),
                current_grade_since=parse_date(_cell(row, "current_grade_since")),
                years_at_level=parse_years(_cell(row, "years_at_level")),
                total_years_experience=parse_years(_cell(row, "total_years_experience")),
                location=cell_text(_cell(row, "location")),
                reporting_manager=cell_text(_cell(row, "reporting_manager")),
                reporting_partner=cell_text(_cell(row, "reporting_partner")),
                employment_status=cell_text(_cell(row, "employment_status")) or "Active",
                row_number=excel_row,
            )
        )
    if not employees:
        raise IngestError("Employee_Master does not contain any usable employee rows.")
    return employees, found_fields


def _read_increments(frame: pd.DataFrame, issues: list[ValidationIssue]) -> list[IncrementRule]:
    frame = _rename_columns(_drop_empty(frame), INCREMENT_COLUMNS)
    _require_columns(frame, ["grade", "performance_rating", "increment_pct"], "Increment_Grid")
    rules: list[IncrementRule] = []
    for offset, row in frame.reset_index(drop=True).iterrows():
        excel_row = int(offset) + 2
        grade = cell_text(_cell(row, "grade"))
        rating = parse_rating(_cell(row, "performance_rating"))
        increment = parse_percent(_cell(row, "increment_pct"))
        if not grade or not is_valid_rating(rating) or increment is None:
            issues.append(
                issue(
                    "Increment_Grid",
                    excel_row,
                    INCOMPLETE_RULE,
                    "Incomplete increment rule - skipped",
                    severity="warning",
                )
            )
            continue
        rules.append(IncrementRule(grade=grade, performance_rating=rating, increment_pct=increment))
    return rules


def _read_bands(frame: pd.DataFrame, issues: list[ValidationIssue]) -> list[SalaryBand]:
    frame = _rename_columns(_drop_empty(frame), BAND_COLUMNS)
    _require_columns(
        frame,
        ["department", "grade", "years_at_level", "min_salary", "median_salary", "max_salary"],
        "Salary_Band",
    )
    bands: list[SalaryBand] = []
    for offset, row in frame.reset_index(drop=True).iterrows():
        excel_row = int(offset) + 2
        department = cell_text(_cell(row, "department"))
        grade = cell_text(_cell(row, "grade"))
        years_raw = _cell(row, "years_at_level")
        years = parse_years(years_raw)
        minimum = parse_salary_lpa(_cell(row, "min_salary"))
        median = parse_salary_lpa(_cell(row, "median_salary"))
        maximum = parse_salary_lpa(_cell(row, "max_salary"))
        if not department or not grade or years is None or minimum is None or median is None or maximum is None:
            issues.append(
                issue(
                    "Salary_Band",
                    excel_row,
                    INCOMPLETE_RULE,
                    "Incomplete salary band - skipped",
                    severity="warning",
                )
            )
            continue
        bands.append(
            SalaryBand(
                department=department,
                grade=grade,
                years_at_level=years,
                min_salary=minimum,
                median_salary=median,
                max_salary=maximum,
                raw_years_label=cell_text(years_raw),
            )
        )
    return bands


def _read_corrections(frame: pd.DataFrame, issues: list[ValidationIssue]) -> list[CorrectionRule]:
    frame = _rename_columns(_drop_empty(frame), CORRECTION_COLUMNS)
    _require_columns(frame, ["min_compa", "max_compa", "correction_pct"], "Salary_Correction_Rules")
    rules: list[CorrectionRule] = []
    for offset, row in frame.reset_index(drop=True).iterrows():
        excel_row = int(offset) + 2
        min_compa = first_number(_cell(row, "min_compa"))
        max_compa = first_number(_cell(row, "max_compa"))
        correction = parse_percent(_cell(row, "correction_pct"))
        if min_compa is None or max_compa is None or correction is None:
            issues.append(
                issue(
                    "Salary_Correction_Rules",
                    excel_row,
                    INCOMPLETE_RULE,
                    "Incomplete correction rule - skipped",
                    severity="warning",
                )
            )
            continue
        rules.append(CorrectionRule(min_compa=min_compa, max_compa=max_compa, correction_pct=correction))
    return rules
