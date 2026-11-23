"""Run the analysis for the selected year and week, at national, Admin1 and Admin2 level."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import yaml
from shapely.geometry import shape

from . import charts
from .dashboard import build_dashboard
from .excel import write_workbook
from .geo import COUNTRY
from .synthetic import make_dataset
from .thresholds import (
    MEASURES,
    aggregate,
    auto_week,
    baseline_years,
    check_pair,
    compute_thresholds,
    detect_abnormal_years,
    read_weekly,
    share_above_alert,
    status_sentence,
    unusual_values,
    weekly_status,
)

LEVELS = ("national", "region", "district")


def run(config_path: str | Path = "config.yaml", out: str | Path = "output") -> dict:
    root = Path(config_path).resolve().parent
    cfg = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    out = Path(out)
    (out / "charts").mkdir(parents=True, exist_ok=True)
    year = cfg["selected_year"]
    alert, epidemic = cfg["alert_threshold"], cfg["epidemic_threshold"]
    check_pair(alert, epidemic)

    if cfg.get("use_sample_data", True):
        paths = make_dataset(out / "sample_data", cfg["seed"], year - 7, year,
                             cfg.get("sample_last_week", 44))
        country = COUNTRY
    else:
        paths = {k: root / v for k, v in cfg["inputs"].items()}
        country = cfg.get("country_name", "Country")

    indicator = cfg.get("indicator", "cases")
    data = read_weekly(paths["workbook"], cfg["sheets"][indicator], cfg["columns"])
    week = auto_week(data, year) if str(cfg["week"]).lower() == "auto" else int(cfg["week"])
    abnormal = [int(y) for y in cfg.get("abnormal_years") or []]
    years = baseline_years(year, sorted(data.year.unique()), abnormal, cfg["baseline_years"])
    if len(years) < cfg["baseline_years"]:
        print(f"Warning: only {len(years)} baseline years available: {years}")

    agg = {lv: aggregate(data, lv) for lv in LEVELS}
    thr = {lv: compute_thresholds(agg[lv], years) for lv in LEVELS}
    status = {lv: weekly_status(agg[lv], thr[lv], year, alert, epidemic, week) for lv in LEVELS}
    region_of = data.drop_duplicates("district").set_index("district").region.to_dict()

    sd = status["district"]
    latest = sd[sd.week == week].copy()
    latest["region"] = latest.unit.map(region_of)
    latest["ratio"] = (latest.value / latest.epidemic_threshold).round(2)
    latest["weeks_a_or_e"] = latest.unit.map(sd[sd.code.isin(["A", "E"])].groupby("unit").size()
                                             ).fillna(0).astype(int)
    rank = {"E": 0, "A": 1, "NA": 2, "N": 3}
    latest = latest.sort_values(["code", "ratio"], key=lambda s: s.map(rank) if s.name == "code"
                                else -s.fillna(0)).reset_index(drop=True)
    share = share_above_alert(sd, cfg["critical_pct"])
    nat = status["national"]
    nat_code = nat[nat.week == week].code.iloc[0]

    gj = json.loads(Path(paths["geometry"]).read_text(encoding="utf-8"))
    geometry = {f["properties"]["district"]: shape(f["geometry"]) for f in gj["features"]}
    c = out / "charts"
    flagged = latest[latest.code.isin(["E", "A"])].unit.tolist()
    ch = {
        "map": charts.status_map(latest, geometry, region_of, c / "status_map.png", week, year),
        "heatmap": charts.status_heatmap(sd, region_of, c / "status_heatmap.png", year),
        "national_regions": charts.curves(
            pd.concat([status["national"], status["region"]]),
            pd.concat([thr["national"], thr["region"]]),
            ["National"] + sorted(status["region"].unit.unique()), alert, epidemic,
            c / "curves_national_regions.png", week, year,
            f"National and regional curves, week {week} of {year}"),
        "districts": charts.curves(sd, thr["district"], flagged, alert, epidemic,
                                   c / "curves_districts.png", week, year,
                                   f"Districts in epidemic or alert at week {week}, {year}"),
        "share": charts.share_above_alert(share, cfg["critical_pct"], c / "share_above_alert.png",
                                          year),
    }
    res = {
        "country": country, "indicator": indicator, "year": year, "last_week": week,
        "alert": alert, "epidemic": epidemic, "baseline_years": years, "abnormal_years": abnormal,
        "critical_pct": cfg["critical_pct"], "agg": agg, "thresholds": thr, "status": status,
        "latest": latest, "share": share, "unusual": unusual_values(data, year),
        "abnormal_check": detect_abnormal_years(data, year, cfg["baseline_years"], 1.5),
        "geometry": geometry, "region_of": region_of, "charts": ch, "inputs": paths,
        "generated": date.today().isoformat(),
        "headline": status_sentence(nat_code, f"national level ({country})", week, year, alert,
                                    epidemic),
    }
    res["workbook"] = write_workbook(out / f"malaria_thresholds_{year}_W{week}.xlsx", res)
    res["dashboard"] = build_dashboard(out / f"malaria_dashboard_{year}_W{week}.html", res)
    res["measures"] = MEASURES
    return res
