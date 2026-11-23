"""Epidemic thresholds: the selected week of the selected year compared with the SAME
week of the five previous (non-abnormal) years.

Measures (letters as in the original Excel tool):
  a  q1        1st quartile of the baseline values for week w
  b  q3        3rd quartile
  c  median    median
  d  csum      C-SUM: mean of weeks w-1, w, w+1 over the baseline years
  e  p85       85th centile
  f  mean_2sd  mean + 2 standard deviations
Zeros are treated as "not reported" and left out of a-c, e and f (C-SUM keeps them).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

MEASURES = {
    "q1": "1st quartile (a)", "q3": "3rd quartile (b)", "median": "Median (c)",
    "csum": "C-SUM (d)", "p85": "85th centile (e)", "mean_2sd": "Mean + 2 SD (f)",
}
# Alert measure -> epidemic measures allowed with it (always a higher threshold).
VALID_PAIRS = {
    "q1": ["median", "q3", "p85", "mean_2sd"],
    "csum": ["median", "q3", "p85", "mean_2sd"],
    "median": ["q3", "p85", "mean_2sd"],
    "q3": ["p85", "mean_2sd"],
}
STATUS = {"N": "Normal", "A": "Alert", "E": "Epidemic", "NA": "Not reported"}


def check_pair(alert: str, epidemic: str) -> None:
    if alert not in VALID_PAIRS:
        raise ValueError(f"Alert measure must be one of {list(VALID_PAIRS)}, got {alert!r}")
    if epidemic not in VALID_PAIRS[alert]:
        raise ValueError(f"With alert = {MEASURES[alert]}, the epidemic measure must be one of "
                         f"{[MEASURES[m] for m in VALID_PAIRS[alert]]}, got {epidemic!r}")


# ------------------------------------------------------------------ reading
def read_weekly(path: Path, sheet: str, columns: dict) -> pd.DataFrame:
    """Wide workbook (district, region, year, W1..W53) -> long table
    district, region, year, week, value."""
    df = pd.read_excel(path, sheet_name=sheet)
    df.columns = [str(c).strip() for c in df.columns]
    pre = columns["week_prefix"]
    wcols = [c for c in df.columns if c.startswith(pre) and c[len(pre):].isdigit()]
    long = df.melt(id_vars=[columns["district"], columns["region"], columns["year"]],
                   value_vars=wcols, var_name="week", value_name="value")
    long = long.rename(columns={columns["district"]: "district", columns["region"]: "region",
                                columns["year"]: "year"})
    long["week"] = long.week.str[len(pre):].astype(int)
    long["year"] = long.year.astype(int)
    long["value"] = pd.to_numeric(long.value, errors="coerce")
    return long.sort_values(["district", "year", "week"], ignore_index=True)


def aggregate(data: pd.DataFrame, level: str) -> pd.DataFrame:
    """Sum district data to `level` (national | region | district) -> unit, year, week, value.

    A unit-week with nothing reported stays missing (it is not summed to 0)."""
    key = {"national": None, "region": "region", "district": "district"}[level]
    d = data.assign(unit="National") if key is None else data.assign(unit=data[key])
    out = d.groupby(["unit", "year", "week"]).value.sum(min_count=1).reset_index()
    out["level"] = level
    return out


# ------------------------------------------------------------------ baseline
def baseline_years(selected_year: int, available: list[int], abnormal: list[int],
                   n: int = 5) -> list[int]:
    """The n most recent years before `selected_year` that are not abnormal. An abnormal
    year is replaced by an earlier one, so the baseline keeps n years when data allow."""
    out = []
    for y in sorted((y for y in available if y < selected_year), reverse=True):
        if y not in abnormal:
            out.append(int(y))
        if len(out) == n:
            break
    return sorted(out)


def detect_abnormal_years(data: pd.DataFrame, selected_year: int, n: int,
                          factor: float) -> pd.DataFrame:
    """Optional helper (not in the Excel tool): flag years whose national total is more than
    `factor` x the median of the other candidate years, as candidates for the abnormal list."""
    nat = aggregate(data, "national")
    years = sorted(y for y in nat.year.unique() if y < selected_year)[-(n + 2):]
    tot = nat[nat.year.isin(years)].groupby("year").value.sum()
    rows = []
    for y, v in tot.items():
        med = tot.drop(y).median()
        rows.append({"year": y, "national_cases": v, "median_other_years": med,
                     "ratio": round(v / med, 2), "suggest_abnormal": v > factor * med})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ thresholds
def _stats(x: np.ndarray, window: np.ndarray) -> dict:
    pos = x[x > 0]
    out = {"n_years": len(pos), "min": np.nan, "max": np.nan}
    if len(pos):
        out.update(min=pos.min(), max=pos.max(), q1=np.percentile(pos, 25),
                   q3=np.percentile(pos, 75), median=float(np.median(pos)),
                   p85=np.percentile(pos, 85),
                   mean_2sd=pos.mean() + 2 * pos.std(ddof=1) if len(pos) > 1 else np.nan)
    w = window[~np.isnan(window)]
    out["csum"] = w.mean() if len(w) else np.nan
    return out


def compute_thresholds(agg: pd.DataFrame, years: list[int]) -> pd.DataFrame:
    """All seven measures for weeks 1-53 for every unit in `agg`, over `years`.

    Week 53: a baseline year without week 53 contributes its week 52.
    C-SUM window wraps: week 1 uses weeks 52, 1, 2."""
    b = agg[agg.year.isin(years)]
    piv = b.pivot_table(index=["unit", "year"], columns="week", values="value",
                        dropna=False).reindex(columns=range(1, 54))
    piv[53] = piv[53].fillna(piv[52])
    rows = []
    for unit, g in piv.groupby(level="unit"):
        m = g.to_numpy(float)
        for w in range(1, 54):
            prev = 52 if w == 1 else w - 1
            nxt = w + 1 if w < 53 else 1
            window = m[:, [prev - 1, w - 1, nxt - 1]].ravel()
            rows.append({"unit": unit, "week": w, **_stats(m[:, w - 1], window)})
    out = pd.DataFrame(rows)
    out["level"] = agg.level.iloc[0]
    return out


def weekly_status(agg: pd.DataFrame, thr: pd.DataFrame, year: int, alert: str,
                  epidemic: str, last_week: int) -> pd.DataFrame:
    """Status per unit and week of `year` (weeks 1..last_week): E if cases > epidemic
    threshold, A if > alert threshold, N otherwise; NA if not reported (missing or 0)."""
    cur = agg[(agg.year == year) & (agg.week <= last_week)]
    x = cur.merge(thr[["unit", "week", alert, epidemic]], on=["unit", "week"], how="left")
    x = x.rename(columns={alert: "alert_threshold", epidemic: "epidemic_threshold"})
    reported = x.value.notna() & (x.value > 0)
    x["code"] = np.where(~reported, "NA",
                         np.where(x.value > x.epidemic_threshold, "E",
                                  np.where(x.value > x.alert_threshold, "A", "N")))
    x["status"] = x.code.map(STATUS)
    return x.sort_values(["unit", "week"], ignore_index=True)


def auto_week(data: pd.DataFrame, year: int) -> int:
    """Last week of `year` with cases reported nationally (the tool's 'Auto' week)."""
    nat = aggregate(data, "national")
    w = nat[(nat.year == year) & (nat.value > 0)].week
    if w.empty:
        raise ValueError(f"No data reported for {year}")
    return int(w.max())


def share_above_alert(status: pd.DataFrame, critical_pct: float) -> pd.DataFrame:
    """Per week: % of reporting districts above their alert threshold (A or E), compared with
    the critical level (the tool's 'AlertLevel')."""
    s = status[status.code != "NA"]
    out = s.groupby("week").code.agg(
        reporting="count", above_alert=lambda c: int(c.isin(["A", "E"]).sum())).reset_index()
    out["pct_above_alert"] = (out.above_alert / out.reporting * 100).round(1)
    out["critical"] = out.pct_above_alert >= critical_pct
    return out


def unusual_values(data: pd.DataFrame, year: int) -> pd.DataFrame:
    """Data check from the tool's case sheet: within each district-year, weeks above
    mean + 2 SD (unusually high) or below mean - 2 SD (possibly missing or under-reported)."""
    d = data[data.year == year].copy()
    g = d.groupby("district").value
    d["row_mean"], d["row_sd"] = g.transform("mean"), g.transform("std")
    d["flag"] = np.where(d.value > d.row_mean + 2 * d.row_sd, "high",
                         np.where(d.value < d.row_mean - 2 * d.row_sd, "low", ""))
    return d[d.flag != ""][["district", "region", "year", "week", "value", "row_mean", "flag"]]


def status_sentence(code: str, unit: str, week: int, year: int, alert: str,
                    epidemic: str) -> str:
    text = {"E": f"Epidemic: above the epidemic threshold ({MEASURES[epidemic]})",
            "A": f"Alert: above the alert threshold ({MEASURES[alert]})",
            "N": "Normal, continue routine surveillance",
            "NA": "Not reported"}[code]
    return f"Week {week} of {year} - {text} - {unit}"
