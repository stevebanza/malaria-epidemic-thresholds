"""Static charts and the status map (PNG)."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import ListedColormap  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
from matplotlib.patches import Polygon as MplPolygon  # noqa: E402
from shapely.geometry import MultiPolygon  # noqa: E402
from shapely.ops import unary_union  # noqa: E402

SURFACE, INK, INK_2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e1"
CASES = "#2a78d6"
STATUS_COLORS = {"Normal": "#cfe3cf", "Alert": "#fab219", "Epidemic": "#d03b3b",
                 "No data": "#d9d8d4"}
METHOD_LABEL = {"q3": "Third quartile", "mean_2sd": "Mean + 2 SD", "csum": "C-SUM + 1.96 SD"}

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": GRID,
    "axes.labelcolor": INK_2, "xtick.color": INK_2, "ytick.color": INK_2,
    "axes.titlesize": 13, "axes.titleweight": "bold", "axes.titlecolor": INK,
    "axes.titlelocation": "left", "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE, "savefig.dpi": 160,
})


def _clean(ax, grid="y"):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(axis=grid, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)


def _title(ax, title, subtitle=None):
    ax.set_title(title, pad=24 if subtitle else 8)
    if subtitle:
        ax.text(0, 1.015, subtitle, transform=ax.transAxes, color=INK_2, fontsize=9.5,
                va="bottom")


def _status_handles(counts=None):
    return [Patch(facecolor=c, label=f"{s} ({counts.get(s, 0)})" if counts is not None else s)
            for s, c in STATUS_COLORS.items()]


def status_heatmap(status: pd.DataFrame, order: list[str], path: Path, year: int) -> Path:
    weeks = sorted(status.week.unique())
    codes = {s: i for i, s in enumerate(STATUS_COLORS)}
    grid = (status.pivot(index="district", columns="week", values="status")
            .reindex(index=order, columns=weeks).map(lambda s: codes.get(s, 3)))
    fig, ax = plt.subplots(figsize=(11, 0.22 * len(order) + 1.8))
    ax.imshow(grid.to_numpy(), aspect="auto", interpolation="nearest",
              cmap=ListedColormap(list(STATUS_COLORS.values())), vmin=0, vmax=3)
    ax.set_xticks(np.arange(len(weeks))[::2] if len(weeks) > 26 else np.arange(len(weeks)),
                  [weeks[i] for i in (range(0, len(weeks), 2) if len(weeks) > 26
                                      else range(len(weeks)))], fontsize=7.5)
    ax.set_yticks(range(len(order)), order, fontsize=7.5)
    ax.set_xticks(np.arange(-0.5, len(weeks)), minor=True)
    ax.set_yticks(np.arange(-0.5, len(order)), minor=True)
    ax.grid(which="minor", color=SURFACE, linewidth=1)
    ax.tick_params(which="both", length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    region = status.drop_duplicates("district").set_index("district").region.reindex(order)
    starts = [i for i in range(len(order)) if i == 0 or region.iloc[i] != region.iloc[i - 1]]
    for k, i in enumerate(starts):
        end = starts[k + 1] if k + 1 < len(starts) else len(order)
        if i:
            ax.axhline(i - 0.5, color=INK, lw=1.4)
        ax.text(len(weeks) - 0.2, (i + end - 1) / 2, region.iloc[i], va="center", fontsize=8.5,
                color=INK, fontweight="bold")
    ax.set_xlabel("Epidemiological week")
    _title(ax, f"Weekly status by district, {year}", "Districts grouped by region")
    ax.legend(handles=_status_handles(), loc="upper center", bbox_to_anchor=(0.5, -0.06),
              ncol=4, frameon=False, fontsize=8.5)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path


def district_panel(ax, cur: pd.DataFrame, thr: pd.DataFrame, alert: str, epidemic: str,
                   title: str, last_week: int, small: bool = True):
    t = thr[thr.week <= max(last_week, 52)]
    ax.fill_between(t.week, t["min"], t["max"], color=GRID, label="Baseline range")
    ax.plot(t.week, t[alert], color="#b77400", lw=1.4, ls=(0, (4, 2)),
            label=f"Alert: {METHOD_LABEL[alert]}")
    ax.plot(t.week, t[epidemic], color="#d03b3b", lw=1.6,
            label=f"Epidemic: {METHOD_LABEL[epidemic]}")
    c = cur[cur.week <= last_week]
    ax.plot(c.week, c.value, color=CASES, lw=2, label="Cases, current year")
    ep = c[c.status == "Epidemic"]
    ax.scatter(ep.week, ep.value, s=18 if small else 30, color="#d03b3b", zorder=3,
               edgecolor=SURFACE, linewidth=1)
    ax.set_xlim(1, 53)
    ax.set_ylim(0, None)
    ax.set_title(title, fontsize=10 if small else 13)
    _clean(ax)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))


def district_curves(status: pd.DataFrame, thr: pd.DataFrame, districts: list[str],
                    alert: str, epidemic: str, path: Path, last_week: int, year: int) -> Path:
    districts = districts[:9]
    n = max(len(districts), 1)
    cols = 3
    rows = int(np.ceil(n / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(12, 3 * rows + 1), squeeze=False)
    for ax, d in zip(axes.ravel(), districts, strict=False):
        cur = status[status.district == d]
        st = cur[cur.week == last_week].status
        district_panel(ax, cur, thr[thr.district == d], alert, epidemic,
                       f"{d} - {st.iloc[0] if len(st) else 'No data'}", last_week)
    for ax in axes.ravel()[n:]:
        ax.axis("off")
    h, lab = axes[0, 0].get_legend_handles_labels()
    fig.legend(h, lab, loc="lower center", ncol=4, frameon=False, fontsize=9)
    fig.suptitle(f"Districts in alert or epidemic at week {last_week}, {year}", x=0.01,
                 ha="left", fontsize=14, fontweight="bold", color=INK)
    fig.tight_layout(rect=(0, 0.05, 1, 0.97))
    fig.savefig(path)
    plt.close(fig)
    return path


def national_curve(cases: pd.DataFrame, year: int, baseline_years: list[int],
                   last_week: int, path: Path) -> Path:
    nat = cases.groupby(["year", "week"]).value.sum(min_count=1).reset_index()
    b = nat[nat.year.isin(baseline_years)].groupby("week").value
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.fill_between(b.min().index, b.min(), b.max(), color=GRID, label="Range, previous years")
    ax.plot(b.median().index, b.median(), color=INK_2, lw=1.4, ls=(0, (4, 2)),
            label="Median, previous years")
    c = nat[(nat.year == year) & (nat.week <= last_week)]
    ax.plot(c.week, c.value, color=CASES, lw=2.2, label=str(year))
    ax.set_xlim(1, 53)
    ax.set_ylim(0, None)
    ax.set_xlabel("Epidemiological week")
    ax.set_ylabel("Confirmed malaria cases")
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    _title(ax, "National weekly malaria cases", f"{year} to week {last_week} vs. "
           f"{min(baseline_years)}-{max(baseline_years)}")
    _clean(ax)
    ax.legend(frameon=False, loc="upper left", fontsize=9)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path


def _draw(ax, geom, **kw):
    for p in (geom.geoms if isinstance(geom, MultiPolygon) else [geom]):
        ax.add_patch(MplPolygon(list(p.exterior.coords), closed=True, **kw))


def status_map(summary: pd.DataFrame, geometry: dict, path: Path, last_week: int,
               year: int) -> Path:
    st = summary.set_index("district").status
    fig, ax = plt.subplots(figsize=(7.5, 6.6))
    for d, g in geometry.items():
        _draw(ax, g, facecolor=STATUS_COLORS.get(st.get(d, "No data")), edgecolor="white",
              linewidth=0.7)
    for region, g in summary.groupby("region"):
        shape = unary_union([geometry[x] for x in g.district if x in geometry])
        _draw(ax, shape, facecolor="none", edgecolor=INK, linewidth=1.3)
        c = shape.representative_point()
        ax.text(c.x, c.y, region, ha="center", va="center", fontsize=8.5, fontweight="bold",
                color=INK, bbox=dict(boxstyle="round,pad=0.2", fc=SURFACE, ec="none", alpha=0.75))
    ax.autoscale_view()
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(f"District status, week {last_week} of {year}")
    ax.legend(handles=_status_handles(st.value_counts()), loc="lower left", frameon=False,
              fontsize=8.5, title="Status (districts)", title_fontsize=8.5)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path
