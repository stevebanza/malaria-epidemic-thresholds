"""Synthetic weekly malaria surveillance data for the fictional Republic of Kivara.

Writes a workbook in the wide layout used by many national IDSR teams: one row per
district and year, one column per epidemiological week (W1..W53), one sheet for cases
and one for deaths. Planted on purpose:
  - a past epidemic year (2022) in some districts, to show why it must be excluded
    from the baseline;
  - a strong current-year rise in 3 districts and a moderate one (+25%) in 4 others;
  - missing weeks in one district.
Everything is invented. planted_events.json lists what was planted.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from .geo import make_geography, write_geojson


def weeks_in_year(y: int) -> int:
    return date(y, 12, 28).isocalendar()[1]


def make_dataset(out_dir: Path, seed: int, first_year: int, current_year: int,
                 last_week: int) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed + 11)
    geo = make_geography(seed)
    names, regions = list(geo.district), list(geo.region)
    n = len(names)
    region_peak = {r: p for r, p in zip(sorted(set(regions)), rng.uniform(27, 38, 6),
                                        strict=True)}
    pop = np.exp(rng.normal(np.log(260_000), 0.6, n)).clip(70_000, 1_100_000)
    annual_rate = rng.uniform(40, 220, n) / 1000  # cases per person-year

    picks = rng.choice(n, 13, replace=False)
    past_epidemic = [names[i] for i in picks[:5]]
    current_epidemic = [names[i] for i in picks[5:8]]
    current_increase = [names[i] for i in picks[8:12]]
    missing = names[picks[12]]

    cases_rows, death_rows = [], []
    for y in range(first_year, current_year + 1):
        nweeks = weeks_in_year(y)
        last = last_week if y == current_year else nweeks
        yf = rng.lognormal(0, 0.12, n) if y < current_year else rng.lognormal(-0.03, 0.03, n)
        for i, d in enumerate(names):
            w = np.arange(1, nweeks + 1)
            peak, width = region_peak[regions[i]], rng.uniform(5, 8)
            shape = 0.35 + 2.2 * np.exp(-((w - peak) / width) ** 2)
            mu = pop[i] * annual_rate[i] / nweeks * shape / shape.mean() * yf[i]
            if y == 2022 and d in past_epidemic:
                mu = mu * (1 + 1.6 * np.exp(-((w - peak) / 6) ** 2))
            if y == current_year and d in current_epidemic:
                mu = mu * (1 + 1.8 / (1 + np.exp(-(w - (last - 6)) / 1.5)))
            if y == current_year and d in current_increase:
                mu = mu * np.where(w >= last - 3, 1.25, 1.0)
            c = rng.poisson(mu).astype(float)
            c[last:] = np.nan
            if y == current_year and d == missing:
                c[[last - 5, last - 4]] = np.nan
            dth = np.where(np.isnan(c), np.nan,
                           rng.binomial(np.nan_to_num(c).astype(int), 0.003)).astype(float)
            row = {"District": d, "Region": regions[i], "Year": y}
            cases_rows.append(row | {f"W{k}": (None if k > nweeks or np.isnan(c[k - 1])
                                               else int(c[k - 1])) for k in range(1, 54)})
            death_rows.append(row | {f"W{k}": (None if k > nweeks or np.isnan(dth[k - 1])
                                               else int(dth[k - 1])) for k in range(1, 54)})

    paths = {"workbook": out_dir / "malaria_weekly.xlsx",
             "geometry": out_dir / "districts.geojson"}
    with pd.ExcelWriter(paths["workbook"]) as xw:
        pd.DataFrame(cases_rows).to_excel(xw, sheet_name="Cases", index=False)
        pd.DataFrame(death_rows).to_excel(xw, sheet_name="Deaths", index=False)
    write_geojson(geo, paths["geometry"])
    planted = {"past_epidemic_2022": past_epidemic, "current_epidemic": current_epidemic,
               "current_moderate_increase": current_increase, "missing_weeks": missing}
    (out_dir / "planted_events.json").write_text(json.dumps(planted, indent=2), encoding="utf-8")
    return paths


def to_french_layout(src: Path, dst: Path) -> Path:
    """Rewrite the workbook with French headers (Districts, Province, Année, S1..S53),
    as countries such as Chad or Burundi often send it. Used to test column mapping."""
    with pd.ExcelWriter(dst) as xw:
        for sheet, fr in (("Cases", "Cas"), ("Deaths", "Deces")):
            df = pd.read_excel(src, sheet_name=sheet)
            df = df.rename(columns={"District": "Districts", "Region": "Province",
                                    "Year": "Année",
                                    **{f"W{k}": f"S{k}" for k in range(1, 54)}})
            df.to_excel(xw, sheet_name=fr, index=False)
    return dst
