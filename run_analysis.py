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
        for d in r["summary"][r["summary"].status == "Epidemic"].itertuples():
            print(f"  EPIDEMIC  {d.district:<10} {d.region:<10} "
                  f"above alert since week {d.episode_start_week}")
        print(f"Workbook:  {r['workbook']}")
        print(f"Dashboard: {r['dashboard']}")
    except BrokenPipeError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
