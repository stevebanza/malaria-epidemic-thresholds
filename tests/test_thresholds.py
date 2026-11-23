"""Tests: each rule of the original Excel tool, then the full pipeline."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from malthresh.pipeline import run
from malthresh.synthetic import to_french_layout
from malthresh.thresholds import (
    aggregate,
    baseline_years,
    check_pair,
    compute_thresholds,
    read_weekly,
    weekly_status,
)

ROOT = Path(__file__).resolve().parents[1]
EN = dict(district="District", region="Region", year="Year", week_prefix="W")
FR = dict(district="Districts", region="Province", year="Année", week_prefix="S")


def _toy(values_by_year: dict, weeks=(1, 2, 3)) -> pd.DataFrame:
    rows = [{"unit": "A", "year": y, "week": w, "value": v, "level": "district"}
            for y, vals in values_by_year.items() for w, v in zip(weeks, vals, strict=True)]
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- rules
def test_abnormal_year_is_replaced_by_an_earlier_year():
    years = list(range(2015, 2027))
    assert baseline_years(2026, years, []) == [2021, 2022, 2023, 2024, 2025]
    assert baseline_years(2026, years, [2022]) == [2020, 2021, 2023, 2024, 2025]
    assert baseline_years(2026, years, [2022, 2024]) == [2019, 2020, 2021, 2023, 2025]


def test_measures_match_excel_definitions():
    agg = _toy({2021: [10, 100, 30], 2022: [20, 200, 0], 2023: [30, 300, 50],
                2024: [40, 400, 70], 2025: [50, 500, 90]})
    t = compute_thresholds(agg, [2021, 2022, 2023, 2024, 2025]).set_index("week")
    w2 = np.array([100, 200, 300, 400, 500.0])
    assert t.at[2, "q1"] == np.percentile(w2, 25)          # PERCENTILE(..., 0.25)
    assert t.at[2, "q3"] == np.percentile(w2, 75)
    assert t.at[2, "median"] == 300
    assert t.at[2, "p85"] == pytest.approx(np.percentile(w2, 85))
    assert t.at[2, "mean_2sd"] == pytest.approx(w2.mean() + 2 * w2.std(ddof=1))  # STDEV
    assert "mean_x2" not in t.columns       # experimental measure, not included
    # C-SUM = plain mean of weeks 1, 2, 3 over the 5 years (zeros included, no SD)
    allv = np.array([10, 20, 30, 40, 50, 100, 200, 300, 400, 500, 30, 0, 50, 70, 90.0])
    assert t.at[2, "csum"] == pytest.approx(allv.mean())


def test_zeros_are_left_out_of_the_statistics():
    agg = _toy({2021: [0, 1, 1], 2022: [10, 1, 1], 2023: [20, 1, 1], 2024: [30, 1, 1],
                2025: [40, 1, 1]})
    t = compute_thresholds(agg, [2021, 2022, 2023, 2024, 2025]).set_index("week")
    assert t.at[1, "median"] == 25          # median of 10, 20, 30, 40 (the 0 is ignored)
    assert t.at[1, "n_years"] == 4


def test_status_is_decided_week_by_week():
    agg = _toy({2026: [5, 15, 25, 0]}, weeks=(1, 2, 3, 4))
    thr = pd.DataFrame({"unit": "A", "week": [1, 2, 3, 4], "median": 10.0, "q3": 20.0})
    st = weekly_status(agg, thr, 2026, "median", "q3", last_week=4)
    assert list(st.code) == ["N", "A", "E", "NA"]   # a single week above is enough; 0 = NA


def test_only_valid_threshold_pairs_are_accepted():
    check_pair("median", "q3")
    check_pair("csum", "mean_2sd")
    with pytest.raises(ValueError):
        check_pair("q3", "median")       # epidemic threshold must be the higher one
    with pytest.raises(ValueError):
        check_pair("mean_2sd", "q3")      # mean + 2 SD is not an alert measure
    with pytest.raises(ValueError):
        check_pair("median", "mean_x2")   # mean x 2 is not offered


def test_levels_are_thresholds_on_summed_cases():
    data = pd.DataFrame({"district": ["d1", "d2"] * 2, "region": "R", "year": [2025, 2025,
                         2026, 2026], "week": 1, "value": [10.0, 20.0, 15.0, np.nan]})
    nat = aggregate(data, "national")
    assert nat.set_index("year").value.to_dict() == {2025: 30.0, 2026: 15.0}


# ---------------------------------------------------------------- pipeline
@pytest.fixture(scope="module")
def result(tmp_path_factory):
    out = tmp_path_factory.mktemp("out")
    r = run(ROOT / "config.yaml", out)
    r["planted"] = json.loads((out / "sample_data" / "planted_events.json").read_text())
    return r


def test_pipeline_uses_auto_week_and_replaced_baseline(result):
    assert result["last_week"] == 44
    assert result["baseline_years"] == [2020, 2021, 2023, 2024, 2025]


def test_planted_epidemics_are_detected(result):
    codes = result["latest"].set_index("unit").code
    for d in result["planted"]["current_epidemic"]:
        assert codes[d] == "E"


def test_all_levels_produced(result):
    assert set(result["status"]["national"].unit) == {"National"}
    assert result["status"]["region"].unit.nunique() == 6
    assert result["status"]["district"].unit.nunique() == 36


def test_french_workbook_gives_identical_thresholds(result, tmp_path):
    fr = to_french_layout(result["inputs"]["workbook"], tmp_path / "fr.xlsx")
    data = read_weekly(fr, "Cas", FR)
    agg = aggregate(data, "district")
    thr = compute_thresholds(agg, result["baseline_years"])
    pd.testing.assert_frame_equal(thr.reset_index(drop=True),
                                  result["thresholds"]["district"].reset_index(drop=True))


def test_outputs(result):
    xl = pd.ExcelFile(result["workbook"])
    assert {"Summary N-A-E", "National", "Admin1 (regions)", "Admin2 (districts)",
            "Data checks"} <= set(xl.sheet_names)
    page = result["dashboard"].read_text(encoding="utf-8")
    assert "Admin1 (region)" in page and result["planted"]["current_epidemic"][0] in page
    for p in result["charts"].values():
        assert Path(p).stat().st_size > 10_000
