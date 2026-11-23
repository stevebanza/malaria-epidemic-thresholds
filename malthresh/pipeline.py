"""Run the whole weekly analysis from config.yaml."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import yaml
from shapely.geometry import shape

from . import charts
from .dashboard import build_dashboard
from .excel import write_workbook
from .geo import COUNTRY
from .synthetic import make_dataset
from .thresholds import (
    baseline_years,
    compute_thresholds,
    latest_summary,
    read_weekly,
    weekly_status,
)


def run(config_path: str | Path = "config.yaml", out: str | Path = "output") -> dict:
    root = Path(config_path).resolve().parent
    cfg = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    out = Path(out)
    (out / "charts").mkdir(parents=True, exist_ok=True)
    year, last_week = cfg["current_year"], cfg["last_week"]

    if cfg.get("use_sample_data", True):
        paths = make_dataset(out / "sample_data", cfg["seed"], year - cfg["baseline_years"] - 2,
                             year, last_week)
        country = COUNTRY
    else:
        paths = {k: root / v for k, v in cfg["inputs"].items()}
        country = cfg.get("country_name", "Country")

    cols = cfg["columns"]
    cases = read_weekly(paths["workbook"], cfg["sheets"]["cases"], cols)
    base = baseline_years(cases, year, cfg["baseline_years"], cfg.get("exclude_years", []),
                          cfg["auto_exclude"]["enabled"], cfg["auto_exclude"]["factor"])
    thr = compute_thresholds(cases, base)
    cur = cases[cases.year == year]
    status = weekly_status(cur, thr, cfg["alert_method"], cfg["epidemic_method"],
                           cfg["consecutive_weeks"], last_week)
    summary = latest_summary(status, last_week)

    gj = json.loads(Path(paths["geometry"]).read_text(encoding="utf-8"))
    geometry = {f["properties"]["district"]: shape(f["geometry"]) for f in gj["features"]}
    order = summary.sort_values(["region", "district"]).district.tolist()
    used_years = sorted(base[base.used].year.unique())
    c = out / "charts"
    flagged = summary[summary.status.isin(["Epidemic", "Alert"])].district.tolist()
    ch = {
        "heatmap": charts.status_heatmap(status, order, c / "status_heatmap.png", year),
        "curves": charts.district_curves(status, thr, flagged, cfg["alert_method"],
                                         cfg["epidemic_method"], c / "district_curves.png",
                                         last_week, year),
        "national": charts.national_curve(cases, year, used_years, last_week,
                                          c / "national_curve.png"),
        "map": charts.status_map(summary, geometry, c / "status_map.png", last_week, year),
    }
    xlsx = write_workbook(out / f"malaria_thresholds_{year}_W{last_week}.xlsx", summary,
                          status, thr, base, year)
    last4 = status[status.week > last_week - 4].value.sum()
    kpis = {"epidemic": int((summary.status == "Epidemic").sum()),
            "alert": int((summary.status == "Alert").sum()), "cases_4w": float(last4),
            "completeness": float(status.value.notna().mean() * 100)}
    ctx = {"country": country, "year": year, "last_week": last_week, "summary": summary,
           "status": status, "thresholds": thr, "alert_method": cfg["alert_method"],
           "epidemic_method": cfg["epidemic_method"], "consecutive": cfg["consecutive_weeks"],
           "geometry": geometry, "charts": ch, "kpis": kpis, "generated": date.today().isoformat(),
           "baseline_label": f"{min(used_years)}-{max(used_years)}"}
    dash = build_dashboard(out / f"malaria_dashboard_{year}_W{last_week}.html", ctx)
    headline = (f"Week {last_week} of {year}: {kpis['epidemic']} district(s) in epidemic, "
                f"{kpis['alert']} on alert, {len(summary) - kpis['epidemic'] - kpis['alert']} "
                f"normal or not reported.")
    return {"summary": summary, "status": status, "thresholds": thr, "baseline": base,
            "workbook": xlsx, "dashboard": dash, "charts": ch, "headline": headline,
            "inputs": paths}
