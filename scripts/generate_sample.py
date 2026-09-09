from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.sample_workbook import build_sample_workbook


def main() -> None:
    target = ROOT / "data" / "sample_compensation_input.xlsx"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(build_sample_workbook())
    print(f"Wrote {target}")


if __name__ == "__main__":
    main()
