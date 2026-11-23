"""Read weekly data, choose baseline years, compute thresholds and weekly status.

Threshold methods (WHO malaria epidemic detection guidance), per district and week w,
over the baseline years:
  q3        third quartile (75th percentile) of the cases in week w
  mean_2sd  mean + 2 standard deviations of the cases in week w
  csum      cumulative-sum method: mean of weeks w-1, w, w+1 (all baseline years),
            upper limit = that mean + 1.96 SD
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

METHODS = ("q3", "mean_2sd", "csum")
STATUS_ORDER = ["Normal", "Alert", "Epidemic", "No data"]


def read_weekly(path: Path, sheet: str, columns: dict) -> pd.DataFrame:
    """Wide workbook (district, region, year, W1..W53) -> long: district, region, year, week,
    value. `columns` maps the file's headers: district, region, year, week_prefix."""
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


def baseline_years(cases: pd.DataFrame, current_year: int, n_years: int,
                   exclude_years: list[int], auto_exclude: bool,
                   auto_factor: float) -> pd.DataFrame:
    """One row per (district, year) kept in the baseline, with the reason for any exclusion.

    Auto-exclusion drops a district-year whose annual total exceeds `auto_factor` x the
    median annual total of that district's other candidate years (a past epidemic).
    """
    years = [y for y in range(current_year - n_years, current_year)]
    tot = (cases[cases.year.isin(years)].groupby(["district", "year"]).value.sum()
           .rename("annual_cases").reset_index())
    rows = []
    for d, g in tot.groupby("district"):
        for r in g.itertuples():
            reason = ""
            if r.year in exclude_years:
                reason = "excluded in config"
            elif auto_exclude:
                others = g[g.year != r.year].annual_cases
                if len(others) and r.annual_cases > auto_factor * others.median():
                    reason = (f"past epidemic: {r.annual_cases:,.0f} cases vs median "
                              f"{others.median():,.0f}")
            rows.append({"district": d, "year": r.year, "annual_cases": r.annual_cases,
                         "used": reason == "", "reason": reason})
    return pd.DataFrame(rows)


def compute_thresholds(cases: pd.DataFrame, baseline: pd.DataFrame) -> pd.DataFrame:
    """Thresholds for weeks 1-53 per district. Week 53 borrows week 52 where a baseline
    year has no week 53."""
    used = baseline[baseline.used][["district", "year"]]
    b = cases.merge(used, on=["district", "year"])
    piv = b.pivot_table(index=["district", "year"], columns="week", values="value")
    piv = piv.reindex(columns=range(1, 54))
    piv[53] = piv[53].fillna(piv[52])
    out = []
    for d, g in piv.groupby(level="district"):
        m = g.to_numpy(float)  # years x 53
        for w in range(1, 54):
            x = m[:, w - 1]
            x = x[~np.isnan(x)]
            win = m[:, [(w - 2) % 53, w - 1, w % 53]].ravel()
            win = win[~np.isnan(win)]
            if len(x) == 0:
                continue
            out.append({
                "district": d, "week": w, "n_years": len(x),
                "min": x.min(), "median": float(np.median(x)), "max": x.max(),
                "q3": float(np.percentile(x, 75)),
                "mean_2sd": float(x.mean() + 2 * x.std(ddof=1)) if len(x) > 1 else np.nan,
                "csum": float(win.mean() + 1.96 * win.std(ddof=1)) if len(win) > 1 else np.nan,
            })
    return pd.DataFrame(out)


def weekly_status(current: pd.DataFrame, thr: pd.DataFrame, alert_method: str,
                  epidemic_method: str, consecutive: int, last_week: int) -> pd.DataFrame:
    """Status per district and week of the current year.

    Epidemic: cases above the epidemic threshold for `consecutive` weeks in a row.
    Alert: cases above the alert threshold (or above the epidemic threshold, not yet for
    enough weeks). Normal otherwise; No data when the week was not reported.
    """
    x = current[current.week <= last_week].merge(
        thr[["district", "week", alert_method, epidemic_method]], on=["district", "week"],
        how="left")
    x = x.rename(columns={alert_method: "alert_threshold",
                          epidemic_method: "epidemic_threshold"})
    x = x.sort_values(["district", "week"], ignore_index=True)
    above_epi = (x.value > x.epidemic_threshold).to_numpy()
    x["weeks_above_epidemic"] = _run_lengths(above_epi, x.district.to_numpy())
    status = np.where(x.value.isna(), "No data",
                      np.where(x.weeks_above_epidemic >= consecutive, "Epidemic",
                               np.where((x.value > x.alert_threshold) | (above_epi == 1),
                                        "Alert", "Normal")))
    x["status"] = status
    return x


def _run_lengths(flags: np.ndarray, keys: np.ndarray) -> np.ndarray:
    """Length of the current run of True values, restarting at each new key (district)."""
    out = np.zeros(len(flags), dtype=int)
    prev, n = None, 0
    for i, (f, k) in enumerate(zip(flags, keys, strict=True)):
        if k != prev:
            prev, n = k, 0
        n = n + 1 if f else 0
        out[i] = n
    return out


def _episode_start(status: pd.Series, last_week: int) -> int | None:
    """First week of the unbroken run of Alert/Epidemic weeks that ends at `last_week`."""
    if status.get(last_week) not in ("Alert", "Epidemic"):
        return None
    w = last_week
    while w - 1 in status.index and status[w - 1] in ("Alert", "Epidemic"):
        w -= 1
    return w


def latest_summary(status: pd.DataFrame, last_week: int) -> pd.DataFrame:
    """Status at the latest week, plus cases of the last 4 weeks vs threshold."""
    rows = []
    for d, g in status.groupby("district"):
        g = g.set_index("week")
        latest = g.loc[last_week] if last_week in g.index else None
        last4 = g.loc[last_week - 3:last_week]
        reported = g[g.value.notna()]
        rows.append({
            "district": d, "region": g.region.iloc[0],
            "status": latest.status if latest is not None else "No data",
            "cases_latest_week": latest.value if latest is not None else np.nan,
            "epidemic_threshold": latest.epidemic_threshold if latest is not None else np.nan,
            "alert_threshold": latest.alert_threshold if latest is not None else np.nan,
            "cases_last_4_weeks": last4.value.sum(min_count=1),
            "threshold_last_4_weeks": last4.epidemic_threshold.sum(),
            "weeks_alert_or_epidemic": int(g.status.isin(["Alert", "Epidemic"]).sum()),
            "episode_start_week": _episode_start(g.status, last_week),
            "completeness": round(len(reported) / last_week * 100, 1),
        })
    out = pd.DataFrame(rows)
    out["episode_start_week"] = out.episode_start_week.astype("Int64")
    out["_o"] = out.status.map({"Epidemic": 0, "Alert": 1, "No data": 2, "Normal": 3})
    return out.sort_values(["_o", "district"]).drop(columns="_o").reset_index(drop=True)
