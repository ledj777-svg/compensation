from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from openpyxl.utils.datetime import from_excel

NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")
HEADER_RE = re.compile(r"[^a-z0-9]+")


def is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    try:
        import math

        if isinstance(value, float) and math.isnan(value):
            return True
    except Exception:
        pass
    try:
        import pandas as pd

        return bool(pd.isna(value))
    except Exception:
        return False


def normalize_header(value: Any) -> str:
    text = str(value or "").replace("\n", " ").replace("\r", " ").strip().lower()
    return HEADER_RE.sub("", text)


def normalize_key(value: Any) -> str:
    return str(value or "").strip().casefold()


def normalize_grade(value: Any) -> str:
    return str(value or "").strip().upper()


def first_number(value: Any) -> float | None:
    if is_blank(value):
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    match = NUMBER_RE.search(text.replace(",", ""))
    if not match:
        return None
    return float(match.group())


def parse_percent(value: Any) -> float | None:
    """Return a decimal fraction: 15% / 15 / 0.15 -> 0.15."""
    if is_blank(value):
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        text = str(value).strip()
        if not text:
            return None
        has_sign = "%" in text
        number = first_number(text)
        if number is None:
            return None
        if has_sign:
            return number / 100.0
    if abs(number) <= 1:
        return number
    return number / 100.0


def parse_salary_lpa(value: Any) -> float | None:
    """Store salaries in LPA. Values >= 1000 are treated as INR."""
    number = first_number(value)
    if number is None:
        return None
    text = str(value).strip().lower() if value is not None else ""
    if "lpa" in text or "lakh" in text:
        return number
    if abs(number) >= 1000:
        return number / 100_000.0
    return number


def parse_years(value: Any) -> float | None:
    if is_blank(value):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = str(value).strip().lower()
    if not text:
        return None
    if "-" in text and not text.startswith("-"):
        parts = [first_number(part) for part in text.split("-")]
        parts = [part for part in parts if part is not None]
        if parts:
            return float(parts[-1])
    return first_number(text)


def parse_rating(value: Any) -> int | None:
    number = first_number(value)
    if number is None:
        return None
    return int(round(number))


def is_valid_rating(rating: int | None) -> bool:
    return rating is not None and 1 <= rating <= 5


def parse_date(value: Any) -> date | None:
    if is_blank(value):
        return None
    if hasattr(value, "to_pydatetime"):
        try:
            return value.to_pydatetime().date()
        except Exception:
            pass
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return from_excel(value).date()
        except Exception:
            return None
    text = str(value).strip()
    if not text:
        return None
    for fmt in (
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%d-%b-%Y",
        "%d %b %Y",
        "%d-%b-%y",
        "%m/%d/%Y",
        "%Y/%m/%d",
    ):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def cell_text(value: Any) -> str:
    if is_blank(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def round_money(value: float | None, digits: int = 4) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def round_pct(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 6)
