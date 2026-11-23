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

from .thresholds import MEASURES, STATUS  # noqa: E402

SURFACE, INK, INK_2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e1"
CASES = "#2a78d6"
ALERT_LINE, EPI_LINE = "#b77400", "#d03b3b"
CODE_COLORS = {"N": "#cfe3cf", "A": "#fab219", "E": "#d03b3b", "NA": "#d9d8d4"}

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


def _handles(counts=None):
    return [Patch(facecolor=c, label=STATUS[k] + (f" ({counts.get(k, 0)})" if counts is not None
                                                 else "")) for k, c in CODE_COLORS.items()]


def _thousands(ax):
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))


def unit_panel(ax, status: pd.DataFrame, thr: pd.DataFrame, alert: str, epidemic: str,
               title: str, last_week: int, year: int, small: bool = True):
    t = thr.sort_values("week")
    ax.fill_between(t.week, t["min"], t["max"], color=GRID, label="Baseline range (5 years)")
    ax.plot(t.week, t[alert], color=ALERT_LINE, lw=1.4, ls=(0, (4, 2)),
            label=f"Alert: {MEASURES[alert]}")
    ax.plot(t.week, t[epidemic], color=EPI_LINE, lw=1.6, label=f"Epidemic: {MEASURES[epidemic]}")
    c = status[(status.week <= last_week) & (status.code != "NA")]
    ax.plot(c.week, c.value, color=CASES, lw=2, label=f"Cases {year}")
    for code, col in (("A", ALERT_LINE), ("E", EPI_LINE)):
        p = c[c.code == code]
        ax.scatter(p.week, p.value, s=16 if small else 28, color=col, zorder=3,
                   edgecolor=SURFACE, linewidth=0.8)
    ax.axvline(last_week, color=INK_2, lw=0.8, ls=":")
    ax.set_xlim(1, 53)
    ax.set_ylim(0, None)
    ax.set_title(title, fontsize=10 if small else 13)
    _clean(ax)
    _thousands(ax)


def curves(status: pd.DataFrame, thr: pd.DataFrame, units: list[str], alert: str,
           epidemic: str, path: Path, last_week: int, year: int, heading: str) -> Path:
    units = units[:9]
    n = max(len(units), 1)
    cols = 3 if n > 4 else min(n, 2) if n > 1 else 1
    rows = int(np.ceil(n / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(4 * cols + 0.5, 3 * rows + 1.1),
                             squeeze=False)
    for ax, u in zip(axes.ravel(), units, strict=False):
        su = status[status.unit == u]
        code = su[su.week == last_week].code
        label = STATUS[code.iloc[0]] if len(code) else "Not reported"
        unit_panel(ax, su, thr[thr.unit == u], alert, epidemic, f"{u} - {label}", last_week,
                   year)
    for ax in axes.ravel()[n:]:
        ax.axis("off")
    h, lab = axes[0, 0].get_legend_handles_labels()
    fig.legend(h, lab, loc="lower center", ncol=4, frameon=False, fontsize=9)
    fig.suptitle(heading, x=0.01, ha="left", fontsize=14, fontweight="bold", color=INK)
    fig.tight_layout(rect=(0, 0.06 if rows > 1 else 0.1, 1, 0.95))
    fig.savefig(path)
    plt.close(fig)
    return path


def status_heatmap(status: pd.DataFrame, region_of: dict, path: Path, year: int) -> Path:
    order = sorted(status.unit.unique(), key=lambda d: (region_of.get(d, ""), d))
    weeks = sorted(status.week.unique())
    codes = {k: i for i, k in enumerate(CODE_COLORS)}
    grid = (status.pivot(index="unit", columns="week", values="code")
            .reindex(index=order, columns=weeks).map(lambda s: codes.get(s, 3)))
    fig, ax = plt.subplots(figsize=(11, 0.22 * len(order) + 1.8))
    ax.imshow(grid.to_numpy(), aspect="auto", interpolation="nearest",
              cmap=ListedColormap(list(CODE_COLORS.values())), vmin=0, vmax=3)
    step = 2 if len(weeks) > 26 else 1
    ax.set_xticks(range(0, len(weeks), step), weeks[::step], fontsize=7.5)
    ax.set_yticks(range(len(order)), order, fontsize=7.5)
    ax.set_xticks(np.arange(-0.5, len(weeks)), minor=True)
    ax.set_yticks(np.arange(-0.5, len(order)), minor=True)
    ax.grid(which="minor", color=SURFACE, linewidth=1)
    ax.tick_params(which="both", length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    regions = [region_of.get(d, "") for d in order]
    starts = [i for i in range(len(order)) if i == 0 or regions[i] != regions[i - 1]]
    for k, i in enumerate(starts):
        end = starts[k + 1] if k + 1 < len(starts) else len(order)
        if i:
            ax.axhline(i - 0.5, color=INK, lw=1.4)
        ax.text(len(weeks) - 0.2, (i + end - 1) / 2, regions[i], va="center", fontsize=8.5,
                color=INK, fontweight="bold")
    ax.set_xlabel("Epidemiological week")
    _title(ax, f"Weekly status by district, {year}", "N/A/E per week, districts grouped by region")
    ax.legend(handles=_handles(), loc="upper center", bbox_to_anchor=(0.5, -0.06), ncol=4,
              frameon=False, fontsize=8.5)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path


def share_above_alert(share: pd.DataFrame, critical: float, path: Path, year: int) -> Path:
    fig, ax = plt.subplots(figsize=(10, 3.6))
    colors = [EPI_LINE if c else CASES for c in share.critical]
    ax.bar(share.week, share.pct_above_alert, color=colors, width=0.75, edgecolor=SURFACE)
    ax.axhline(critical, color=INK_2, lw=1, ls=(0, (4, 3)))
    ax.text(share.week.min(), critical + 2, f"Critical level {critical:.0f}%", fontsize=8.5,
            color=INK_2)
    ax.set_ylim(0, 100)
    ax.set_xlim(0.3, max(53, share.week.max()) + 0.7)
    ax.set_xlabel("Epidemiological week")
    ax.set_ylabel("% of districts")
    _title(ax, "Districts above their alert threshold",
           f"{year}; red bars = critical level reached")
    _clean(ax)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path


def _draw(ax, geom, **kw):
    for p in (geom.geoms if isinstance(geom, MultiPolygon) else [geom]):
        ax.add_patch(MplPolygon(list(p.exterior.coords), closed=True, **kw))


def status_map(latest: pd.DataFrame, geometry: dict, region_of: dict, path: Path,
               last_week: int, year: int) -> Path:
    code = latest.set_index("unit").code
    fig, ax = plt.subplots(figsize=(7.5, 6.6))
    for d, g in geometry.items():
        _draw(ax, g, facecolor=CODE_COLORS[code.get(d, "NA")], edgecolor="white", linewidth=0.7)
    for region in sorted(set(region_of.values())):
        shape = unary_union([geometry[d] for d, r in region_of.items() if r == region])
        _draw(ax, shape, facecolor="none", edgecolor=INK, linewidth=1.3)
        c = shape.representative_point()
        ax.text(c.x, c.y, region, ha="center", va="center", fontsize=8.5, fontweight="bold",
                color=INK, bbox=dict(boxstyle="round,pad=0.2", fc=SURFACE, ec="none", alpha=0.75))
    ax.autoscale_view()
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(f"District status, week {last_week} of {year}")
    ax.legend(handles=_handles(code.value_counts()), loc="lower left", frameon=False,
              fontsize=8.5, title="Status (districts)", title_fontsize=8.5)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path
