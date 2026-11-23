"""Run the weekly malaria epidemic-threshold analysis.

    python run_analysis.py                   # sample data, outputs in output/
    python run_analysis.py --config my.yaml  # your own workbook (see config.yaml)
"""
import argparse
import sys

from malthresh.pipeline import run


def main() -> int:
    ap = argparse.ArgumentParser(description="Malaria epidemic thresholds")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--out", default="output")
    a = ap.parse_args()
    r = run(a.config, a.out)
    try:
        print(r["headline"])
        lt = r["latest"]
        print(f"Baseline years: {r['baseline_years']} (abnormal years skipped: "
              f"{r['abnormal_years'] or 'none'})")
        for x in lt[lt.code.isin(["E", "A"])].itertuples():
            print(f"  {x.code}  {x.unit:<10} {x.region:<10} {x.value:>8,.0f} cases, "
                  f"{x.ratio:.2f} x epidemic threshold")
        print(f"Workbook:  {r['workbook']}")
        print(f"Dashboard: {r['dashboard']}")
    except BrokenPipeError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
