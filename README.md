# Compensation Planning Platform — Phase 1

Rule-based salary recommendation engine for HR and compensation teams.

The app reads one Excel workbook, applies increment and salary-correction rules, and produces:

- Increment %
- Salary correction %
- Compa ratio
- Recommended salary
- Employee comparison
- Excel reports
- Budget analysis

Phase 1 does **not** use machine learning, attrition prediction, RAG, or LLMs. Attrition work is reserved for Phase 2.

## Run

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
py scripts\generate_sample.py
py -m uvicorn app.main:app --reload
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

A sample workbook is written to `data/sample_compensation_input.xlsx`.

## Workbook sheets

| Sheet | Purpose |
|---|---|
| `Employee_Master` | Employees and current pay |
| `Increment_Grid` | Grade × performance rating → increment % |
| `Salary_Band` | Department × grade × years at level → min / median / max |
| `Salary_Correction_Rules` | Compa-ratio range → correction % |

Salaries are stored and reported in **LPA**. Values such as `11 LPA` or `1100000` are accepted.

## Recommendation formula

1. Match salary band by department, grade, and years at level.
2. Compa ratio = current salary ÷ median salary.
3. Classify salary position against min / median / max.
4. Look up correction % from compa-ratio rules (`min <= ratio < max`).
5. Look up increment % from grade and performance rating.
6. Total increase % = increment % + correction %.
7. Recommended salary = current salary × (1 + total increase %).

Example from the spec: current `10 LPA`, median `14 LPA`, rating `4` → increment `10%` + correction `8%` = `18%` → recommended `11.8 LPA`.

Special rules:

1. Below the band minimum: salary correction still applies, even if the rating is low.
2. Above the band maximum: no salary correction; only the performance increment applies.
3. Employees with the same department, grade, and years at level always use the same salary band.

Validation flags missing employee ID, missing salary, missing grade, invalid ratings (not 1–5), and duplicate IDs, and writes a validation report.

Budget impact splits **increment cost** from **salary correction cost**, then totals current payroll, proposed payroll, and compensation cost, including department-wise and grade-wise views.

## Tests

```powershell
py -m pytest -q
```
