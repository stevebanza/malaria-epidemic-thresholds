"""Excel output laid out like the original tool: a threshold block per unit (5 baseline
years, selected year, alert and epidemic thresholds), an N/A/E summary, and data checks."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .charts import CODE_COLORS
from .thresholds import MEASURES, STATUS

FILL = {k: PatternFill("solid", fgColor=c.lstrip("#")) for k, c in CODE_COLORS.items()}
HEAD = PatternFill("solid", fgColor="1F4E79")
BOLD, WHITE = Font(bold=True), Font(bold=True, color="FFFFFF")
UNUSUAL = Font(italic=True, color="C00000")


def _block(ws, row: int, unit: str, agg: pd.DataFrame, thr: pd.DataFrame, status: pd.DataFrame,
           years: list[int], year: int, alert: str, epidemic: str) -> int:
    """One threshold block; returns the next free row."""
    ws.cell(row, 1, unit).font = Font(bold=True, size=12)
    row += 1
    ws.cell(row, 1, "Year").font = WHITE
    ws.cell(row, 1).fill = HEAD
    for w in range(1, 54):
        c = ws.cell(row, w + 1, w)
        c.font, c.fill, c.alignment = WHITE, HEAD, Alignment(horizontal="center")
    a = agg[agg.unit == unit].pivot_table(index="year", columns="week", values="value")
    t = thr[thr.unit == unit].set_index("week")
    base = a.reindex(index=years, columns=range(1, 54))
    mean, sd = base.where(base > 0).mean(), base.where(base > 0).std()
    for y in years:
        row += 1
        ws.cell(row, 1, int(y)).font = BOLD
        for w in range(1, 54):
            v = base.at[y, w]
            if pd.notna(v):
                c = ws.cell(row, w + 1, float(v))
                c.number_format = "#,##0"
                if pd.notna(sd[w]) and (v > mean[w] + 2 * sd[w] or v < mean[w] - 2 * sd[w]):
                    c.font = UNUSUAL
    row += 1
    ws.cell(row, 1, f"{year} (selected)").font = BOLD
    st = status[status.unit == unit].set_index("week")
    for w, r in st.iterrows():
        c = ws.cell(row, w + 1, None if r.code == "NA" else float(r.value))
        c.fill, c.number_format = FILL[r.code], "#,##0"
    for label, m in ((f"Alert threshold: {MEASURES[alert]}", alert),
                     (f"Epidemic threshold: {MEASURES[epidemic]}", epidemic)):
        row += 1
        ws.cell(row, 1, label).font = BOLD
        for w in range(1, 54):
            v = t[m].get(w, np.nan)
            if pd.notna(v):
                ws.cell(row, w + 1, round(float(v), 1)).number_format = "#,##0"
    return row + 2


def write_workbook(path: Path, res: dict) -> Path:
    y, wk, alert, epi = res["year"], res["last_week"], res["alert"], res["epidemic"]
    wb = Workbook()
    ws = wb.active
    ws.title = "Settings"
    for i, (k, v) in enumerate([
        ("Indicator", res["indicator"]), ("Selected year", y), ("Week", wk),
        ("Alert threshold", MEASURES[alert]), ("Epidemic threshold", MEASURES[epi]),
        ("Baseline years", ", ".join(map(str, res["baseline_years"]))),
        ("Abnormal years (excluded)", ", ".join(map(str, res["abnormal_years"])) or "none"),
        ("Critical % of districts above alert", res["critical_pct"]),
        ("Status", "N = normal, A = alert (> alert threshold), E = epidemic (> epidemic "
                   "threshold), NA = not reported"),
        ("Note", "In the threshold sheets, baseline values in red italics are unusual "
                 "(outside mean +/- 2 SD for that week)."),
    ], start=1):
        ws.cell(i, 1, k).font = BOLD
        ws.cell(i, 2, v)
    ws.column_dimensions["A"].width = 36
    ws.column_dimensions["B"].width = 60

    # Week summary for districts
    lt = res["latest"]
    s = wb.create_sheet(f"Week {wk} status")
    cols = ["District", "Region", "Status", "Cases", "Alert threshold", "Epidemic threshold",
            "Cases / epidemic threshold", "Weeks A or E this year"]
    for j, c in enumerate(cols, 1):
        s.cell(1, j, c).font = BOLD
    for i, r in enumerate(lt.itertuples(), 2):
        vals = [r.unit, r.region, STATUS[r.code], r.value, r.alert_threshold,
                r.epidemic_threshold, r.ratio, r.weeks_a_or_e]
        for j, v in enumerate(vals, 1):
            s.cell(i, j, None if (isinstance(v, float) and np.isnan(v)) else v)
        s.cell(i, 3).fill = FILL[r.code]
        for j in (4, 5, 6):
            s.cell(i, j).number_format = "#,##0"
        s.cell(i, 7).number_format = "0.00"
    for j, wdt in enumerate([14, 12, 14, 10, 15, 17, 24, 22], 1):
        s.column_dimensions[get_column_letter(j)].width = wdt

    # N/A/E summary (as in the tool's Summary sheet)
    sm = wb.create_sheet("Summary N-A-E")
    st = res["status"]["district"]
    sm.cell(1, 1, "District").font = BOLD
    sm.cell(1, 2, "Region").font = BOLD
    for w in range(1, wk + 1):
        sm.cell(1, w + 2, w).font = BOLD
    order = lt.sort_values(["region", "unit"])
    for i, r in enumerate(order.itertuples(), 2):
        sm.cell(i, 1, r.unit)
        sm.cell(i, 2, r.region)
        for x in st[st.unit == r.unit].itertuples():
            c = sm.cell(i, x.week + 2, x.code)
            c.fill, c.alignment = FILL[x.code], Alignment(horizontal="center")
    sm.column_dimensions["A"].width, sm.column_dimensions["B"].width = 14, 12
    for w in range(1, wk + 1):
        sm.column_dimensions[get_column_letter(w + 2)].width = 4.5
    sm.freeze_panes = "C2"

    # Threshold blocks per level
    for level, title in (("national", "National"), ("region", "Admin1 (regions)"),
                         ("district", "Admin2 (districts)")):
        sh = wb.create_sheet(title)
        row = 1
        for unit in sorted(res["thresholds"][level].unit.unique()):
            row = _block(sh, row, unit, res["agg"][level], res["thresholds"][level],
                         res["status"][level], res["baseline_years"], y, alert, epi)
        sh.column_dimensions["A"].width = 40
        sh.freeze_panes = "B1"

    sa = wb.create_sheet("% districts above alert")
    for j, c in enumerate(["Week", "Reporting districts", "Above alert (A or E)",
                           "% above alert", f"Critical (>= {res['critical_pct']}%)"], 1):
        sa.cell(1, j, c).font = BOLD
    for i, r in enumerate(res["share"].itertuples(), 2):
        for j, v in enumerate([r.week, r.reporting, r.above_alert, r.pct_above_alert,
                               "YES" if r.critical else ""], 1):
            sa.cell(i, j, v)

    dc = wb.create_sheet("Data checks")
    for j, c in enumerate(["District", "Region", "Year", "Week", "Cases", "Mean of the year",
                           "Flag"], 1):
        dc.cell(1, j, c).font = BOLD
    for i, r in enumerate(res["unusual"].itertuples(), 2):
        flag = ("high: > mean + 2 SD of the year" if r.flag == "high"
                else "low: < mean - 2 SD (missing or under-reported?)")
        for j, v in enumerate([r.district, r.region, r.year, r.week, r.value,
                               round(r.row_mean), flag], 1):
            dc.cell(i, j, v)

    ab = wb.create_sheet("Abnormal year check")
    df = res["abnormal_check"]
    for j, c in enumerate(df.columns, 1):
        ab.cell(1, j, c).font = BOLD
    for i, r in enumerate(df.itertuples(index=False), 2):
        for j, v in enumerate(r, 1):
            ab.cell(i, j, v.item() if hasattr(v, "item") else v)
    wb.save(path)
    return path
