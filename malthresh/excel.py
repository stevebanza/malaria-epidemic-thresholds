"""Excel output: thresholds and weekly status, colour-coded for the surveillance team."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill

from .charts import STATUS_COLORS
from .thresholds import METHODS

FILLS = {s: PatternFill("solid", fgColor=c.lstrip("#")) for s, c in STATUS_COLORS.items()}


def _wide(df: pd.DataFrame, value: str, order: pd.DataFrame) -> pd.DataFrame:
    w = df.pivot(index="district", columns="week", values=value)
    w.columns = [f"W{c}" for c in w.columns]
    return order.merge(w.reset_index(), on="district", how="left")


def write_workbook(path: Path, summary: pd.DataFrame, status: pd.DataFrame,
                   thr: pd.DataFrame, baseline: pd.DataFrame, year: int) -> Path:
    order = summary[["district", "region"]].sort_values(["region", "district"])
    with pd.ExcelWriter(path) as xw:
        summary.to_excel(xw, sheet_name="Summary", index=False)
        _wide(status, "status", order).to_excel(xw, sheet_name=f"Status {year}", index=False)
        _wide(status, "value", order).to_excel(xw, sheet_name=f"Cases {year}", index=False)
        for m in METHODS:
            _wide(thr.assign(v=thr[m].round(0)), "v", order).to_excel(
                xw, sheet_name=f"Threshold {m}", index=False)
        baseline.to_excel(xw, sheet_name="Baseline years", index=False)

    wb = load_workbook(path)
    st = wb[f"Status {year}"]
    cs = wb[f"Cases {year}"]
    for r in range(2, st.max_row + 1):
        for c in range(3, st.max_column + 1):
            s = st.cell(r, c).value
            if s in FILLS:
                st.cell(r, c).fill = FILLS[s]
                cs.cell(r, c).fill = FILLS[s]
                st.cell(r, c).value = s[0] if s != "No data" else "-"  # N / A / E
    sm = wb["Summary"]
    for r in range(2, sm.max_row + 1):
        s = sm.cell(r, 3).value
        if s in FILLS:
            sm.cell(r, 3).fill = FILLS[s]
    for ws in wb.worksheets:
        for cell in ws[1]:
            cell.font = Font(bold=True)
        ws.freeze_panes = "C2"
        ws.column_dimensions["A"].width = 14
        ws.column_dimensions["B"].width = 12
    st.cell(st.max_row + 2, 1, "N = normal, A = alert, E = epidemic, - = not reported")
    wb.save(path)
    return path
