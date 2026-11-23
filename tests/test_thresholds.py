"""Unit and end-to-end tests."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from malthresh.pipeline import run
from malthresh.synthetic import to_french_layout
from malthresh.thresholds import baseline_years, compute_thresholds, read_weekly, weekly_status

ROOT = Path(__file__).resolve().parents[1]
EN = dict(district="District", region="Region", year="Year", week_prefix="W")
FR = dict(district="Districts", region="Province", year="Année", week_prefix="S")


@pytest.fixture(scope="module")
def result(tmp_path_factory):
    out = tmp_path_factory.mktemp("out")
    r = run(ROOT / "config.yaml", out)
    r["out"] = out
    planted = out / "sample_data" / "planted_events.json"
    r["planted"] = json.loads(planted.read_text(encoding="utf-8"))
    r["cases"] = read_weekly(r["inputs"]["workbook"], "Cases", EN)
    return r


def test_thresholds_match_hand_calculation(result):
    cases, base, thr = result["cases"], result["baseline"], result["thresholds"]
    d = "Kita"
    years = base[(base.district == d) & base.used].year
    x = cases[(cases.district == d) & cases.year.isin(years)]
    w30 = x[x.week == 30].value.to_numpy(float)
    win = x[x.week.isin([29, 30, 31])].value.to_numpy(float)
    row = thr[(thr.district == d) & (thr.week == 30)].iloc[0]
    assert row.q3 == pytest.approx(np.percentile(w30, 75))
    assert row.mean_2sd == pytest.approx(w30.mean() + 2 * w30.std(ddof=1))
    assert row.csum == pytest.approx(win.mean() + 1.96 * win.std(ddof=1))


def test_every_district_has_53_weeks(result):
    assert (result["thresholds"].groupby("district").week.count() == 53).all()


def test_past_epidemic_years_are_auto_excluded(result):
    b = result["baseline"]
    excluded = set(b[~b.used].district)
    assert excluded == set(result["planted"]["past_epidemic_2022"])
    assert set(b[~b.used].year) == {2022}


def test_current_epidemics_detected(result):
    s = result["summary"].set_index("district").status
    for d in result["planted"]["current_epidemic"]:
        assert s[d] == "Epidemic"


def test_missing_weeks_reported(result):
    s = result["summary"].set_index("district")
    d = result["planted"]["missing_weeks"]
    assert s.loc[d, "completeness"] < 100
    st = result["status"]
    assert (st[st.district == d].status == "No data").sum() == 2


def test_consecutive_rule():
    cur = pd.DataFrame({"district": "A", "region": "R", "year": 2026, "week": [1, 2, 3, 4],
                        "value": [10.0, 30.0, 30.0, 5.0]})
    thr = pd.DataFrame({"district": "A", "week": [1, 2, 3, 4], "q3": 15.0, "mean_2sd": 20.0})
    st = weekly_status(cur, thr, "q3", "mean_2sd", consecutive=2, last_week=4)
    assert list(st.status) == ["Normal", "Alert", "Epidemic", "Normal"]


def test_config_exclusion():
    cases = pd.DataFrame({"district": "A", "region": "R", "year": [2021, 2022, 2023],
                          "week": 1, "value": [10.0, 50.0, 12.0]})
    b = baseline_years(cases, 2024, 3, [2022], False, 1.5)
    assert b.set_index("year").used.to_dict() == {2021: True, 2022: False, 2023: True}


def test_french_workbook_gives_same_thresholds(result, tmp_path):
    fr = to_french_layout(result["inputs"]["workbook"], tmp_path / "fr.xlsx")
    cases_fr = read_weekly(fr, "Cas", FR)
    base = baseline_years(cases_fr, 2026, 5, [], True, 1.5)
    thr = compute_thresholds(cases_fr, base)
    pd.testing.assert_frame_equal(thr.reset_index(drop=True),
                                  result["thresholds"].reset_index(drop=True))


def test_outputs(result):
    xl = pd.ExcelFile(result["workbook"])
    assert {"Summary", "Status 2026", "Threshold q3", "Baseline years"} <= set(xl.sheet_names)
    page = result["dashboard"].read_text(encoding="utf-8")
    for d in result["planted"]["current_epidemic"]:
        assert d in page
    for p in result["charts"].values():
        assert Path(p).stat().st_size > 10_000
