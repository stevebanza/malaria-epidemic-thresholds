"""Fictional geography shared with the other portfolio repos: the Republic of Kivara,
6 regions and 36 districts (Voronoi cells inside a random outline, local km coordinates).
Same seed -> same map as in ri-coverage-analytics."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import Voronoi
from shapely.geometry import MultiPolygon, Point, Polygon, mapping
from shapely.ops import unary_union

COUNTRY = "Republic of Kivara"
REGIONS = ["Northland", "Lakeside", "Highvale", "Riverbend", "Coastal", "Savanna"]
SYLLABLES = ["ka", "mu", "ri", "to", "ne", "sa", "lo", "be", "ndi", "ga", "wa", "zu",
             "ko", "ma", "ta", "ve", "ru", "ki", "so", "la", "mbe", "yo", "fu", "di"]


# ------------------------------------------------------------------ geography
def _outline(rng: np.random.Generator) -> Polygon:
    t = np.linspace(0, 2 * np.pi, 240, endpoint=False)
    p = rng.uniform(0, 2 * np.pi, 3)
    r = 300 * (1 + 0.16 * np.sin(3 * t + p[0]) + 0.09 * np.cos(5 * t + p[1])
               + 0.04 * np.sin(9 * t + p[2]))
    return Polygon(np.c_[r * np.cos(t) * 1.15, r * np.sin(t)]).buffer(0)


def _voronoi_cells(points: np.ndarray, clip: Polygon) -> list[Polygon]:
    far = np.array([[-1e4, -1e4], [-1e4, 1e4], [1e4, -1e4], [1e4, 1e4]])
    vor = Voronoi(np.vstack([points, far]))
    cells = []
    for i in range(len(points)):
        region = vor.regions[vor.point_region[i]]
        cell = Polygon(vor.vertices[region]).intersection(clip)
        if isinstance(cell, MultiPolygon):
            cell = max(cell.geoms, key=lambda g: g.area)
        cells.append(cell)
    return cells


def _names(rng: np.random.Generator, n: int) -> list[str]:
    out: set[str] = set()
    while len(out) < n:
        k = rng.integers(2, 4)
        out.add("".join(rng.choice(SYLLABLES, k)).capitalize())
    return sorted(out)


def make_geography(seed: int, n_districts: int = 36) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    outline = _outline(rng)
    minx, miny, maxx, maxy = outline.bounds
    pts = []
    while len(pts) < n_districts:
        p = rng.uniform([minx, miny], [maxx, maxy])
        if outline.contains(Point(p)):
            pts.append(p)
    pts = np.array(pts)
    for _ in range(6):  # Lloyd relaxation for even-sized districts
        cells = _voronoi_cells(pts, outline)
        pts = np.array([[c.centroid.x, c.centroid.y] for c in cells])
    cells = _voronoi_cells(pts, outline)

    # Regions: k-means on district centroids.
    k = len(REGIONS)
    centers = pts[rng.choice(len(pts), k, replace=False)]
    for _ in range(25):
        lab = np.argmin(((pts[:, None] - centers[None]) ** 2).sum(-1), axis=1)
        centers = np.array([pts[lab == j].mean(0) if (lab == j).any() else centers[j]
                            for j in range(k)])
    order = np.argsort(-centers[:, 1] * 10 + centers[:, 0])  # roughly north to south
    region_of = {int(j): REGIONS[r] for r, j in enumerate(order)}
    names = _names(rng, n_districts)
    rng.shuffle(names)
    return pd.DataFrame({"district": names, "region": [region_of[int(j)] for j in lab],
                         "geometry": cells}).sort_values(["region", "district"],
                                                         ignore_index=True)


def write_geojson(geo: pd.DataFrame, path: Path) -> None:
    feats = [{"type": "Feature", "properties": {"district": r.district, "region": r.region},
              "geometry": mapping(r.geometry)} for r in geo.itertuples()]
    path.write_text(json.dumps({"type": "FeatureCollection", "name": COUNTRY,
                                "crs_note": "local projected coordinates (km), fictional",
                                "features": feats}), encoding="utf-8")


def region_outlines(geo: pd.DataFrame) -> dict[str, Polygon]:
    return {r: unary_union(list(g.geometry)) for r, g in geo.groupby("region")}
