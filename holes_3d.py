#!/usr/bin/env python
"""Leapfrog-style 3D view of drill holes, coloured by mineral group down hole.

Reads a group of NVCL holes, places every logged metre in 3D (MGA easting,
northing, elevation) and writes one interactive HTML page: each hole is a
tube coloured by its dominant TSA mineral group per metre, collars are
labelled, a surface is drawn through the collar elevations, and - with
--model - a mineral group is interpolated between the holes into a 3D
domain, the way Leapfrog builds its implicit solids.

Observed and interpreted stay visibly apart: the tubes are logged data,
and anything drawn *between* holes (the collar surface, a --model domain)
says "interpolated" in the legend.

Nothing new to install - numpy, pandas, scipy and pyproj already come in
with backend/requirements.txt. The page loads plotly.js from a public CDN
when it's opened (first one that answers); if the `plotly` Python package
happens to be installed, its bundled copy is inlined instead, so the page
also works offline.

Where the holes come from:

  - --data-dir (default ../database5553/etl4, the ETL4 package, else
    data/raw): a folder of NVCL hole folders, each with borehole.json +
    scalars/*.csv. download.py writes the same layout to data/raw, which
    has the tight drill patterns (WTB-*, the Boddington WRD* holes).
  - --db: the Docker Postgres from docker-compose.yml (tables holes +
    measurements, filled by load_data). Start it with `docker compose up -d`.

borehole.json has no dip, azimuth or elevation, so those come from the
GSWA collar catalog (data/holes.csv first, then gswa-hylogger.xlsx). A
hole missing from both is drawn straight down from the median collar
elevation, and the summary says so. An elevation of exactly 0 counts as
missing - it's the catalog's placeholder (WRD13645-002 sits at 0 m while
its neighbours are ~300 m).

Usage:
    python holes_3d.py                                   # biggest cluster in the ETL4 package
    python holes_3d.py --list-clusters
    python holes_3d.py --data-dir data/raw --near WTB-05
    python holes_3d.py --data-dir data/raw --near WRD12980-001 --model CHLORITE
    python holes_3d.py --db --holes BBDD0001 BBDD0002 --dark
"""

from __future__ import annotations

import argparse
import html
import json
import math
import os
import re
import sys
import webbrowser
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import Transformer
from scipy.interpolate import RBFInterpolator, griddata
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import atomic_write_text, read_json, safe_name  # noqa: E402
from mineral_strip import MINERAL_COLOURS, find_first, load_scalar_log, resolve_group  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_DATA_DIRS = [PROJECT_ROOT.parent / "database5553" / "etl4", PROJECT_ROOT / "data" / "raw"]
OUTPUT_DIR = PROJECT_ROOT / "data" / "holes_3d"

# Where dip/azimuth/elevation come from, in priority order. Each field is
# taken from the first table that has it for that hole.
COLLAR_TABLES = [
    PROJECT_ROOT / "data" / "holes.csv",
    PROJECT_ROOT.parent / "database5553" / "wa-drillhole-map" / "data" / "gswa-hylogger.xlsx",
    PROJECT_ROOT.parent / "data5553" / "hylogger_ver1" / "collars.xlsx",
]
# GSWA catalog spreadsheet column -> data/holes.csv column. Its "Total (m)"
# (and so borehole_length_m, and borehole.json's boreholeLength_m) is metres
# of core *scanned* - Depth to minus Depth from in 93% of rows - not how deep
# the hole goes, so a hole is drawn down to "Depth to" or its deepest logged
# metre, whichever is further.
CATALOG_COLUMNS = {
    "Well Name and Info": "hole_id", "Latitude (degrees)": "latitude", "Longitude (degrees)": "longitude",
    "Elevation": "elevation_m", "Inclination (dip)": "inclination_deg", "Azimuth": "azimuth_deg",
    "Total (m)": "borehole_length_m", "Depth to (m)": "scanned_to_m", "Project": "project",
}
# A catalog row only describes a hole if its collar is this close. Names aren't
# unique: "BH01" is a Bunbury bore and "BH01 [dup. name]" a Behemoth hole ~1,300 km away.
CATALOG_MATCH_KM = 2.0

# The order files/extract.py uses for the website's per-metre calls, so a
# metre gets the same colour here as on the site: TSA SWIR group first,
# then the TSA mineral rolled up to its group through MIN2GRP.
GROUP_LOGS = ["*Grp1_sTSAS.csv", "*Grp1_uTSAS.csv", "*Grp1_sTSAV.csv", "*Grp1_uTSAV.csv"]
SPECIES_LOGS = ["*Min1_sTSAS.csv", "*Min1_uTSAS.csv", "*Min1_sTSAV.csv", "*Min1_uTSAV.csv"]

BIN_M = 1.0        # one mineral call per metre, as on the site
COMPOSITE_M = 5.0  # --model works on 5 m composites so neighbouring holes carry weight
GRID_CELLS = 60    # --model grid resolution along the scene's longest side

# Under this share of agreeing readings a metre is drawn thin and grey,
# not coloured. frontend/config.js CONFIDENCE_THRESHOLD - keep in sync.
CONFIDENCE_THRESHOLD = 0.5
UNCERTAIN = "Mixed readings"
# Lighter than the site's LOW_CONFIDENCE_COLOUR (#39424c): once shaded in 3D
# that one can't be told apart from TOURMALINE (#2f2f3f).
UNCERTAIN_COLOUR = "#b3bac1"
# For groups the site palette doesn't list (e.g. PAL-SEP), so two of
# them never end up sharing UNKNOWN_COLOUR in the legend.
EXTRA_COLOURS = ["#d08c60", "#8e7cc3", "#c27ba0", "#76a5af", "#b6a55c", "#e06666"]
SURFACE_COLOUR = "#cdbfa6"  # tan, not terrain green - green is WHITE-MICA / EPIDOTE here

TUBE_SIDES = 10
# Mostly ambient, so a tube's shaded side still reads as its palette colour.
LIGHTING = {"ambient": 0.65, "diffuse": 0.7, "specular": 0.12, "roughness": 0.6, "fresnel": 0.05}
LIGHT_POSITION = {"x": -5e4, "y": -5e4, "z": 1e5}  # above and behind the default camera
THEMES = {
    "light": {"bg": "#ffffff", "fg": "#20242b", "muted": "#5a6472", "wall": "#f3f5f7",
              "grid": "#d3d8de", "legend": "rgba(255,255,255,0.85)", "trace": "#8a9199"},
    "dark": {"bg": "#000000", "fg": "#e6e8eb", "muted": "#9aa3ad", "wall": "#07090c",
             "grid": "#2b3139", "legend": "rgba(0,0,0,0.6)", "trace": "#6b737c"},
}
# Tried in order when the page opens. Some networks' DNS refuses one CDN but
# not another (cdn.plot.ly doesn't resolve on the one this was written on).
PLOTLY_SOURCES = [
    "https://cdnjs.cloudflare.com/ajax/libs/plotly.js/2.35.2/plotly.min.js",
    "https://cdn.jsdelivr.net/npm/plotly.js-dist-min@2.35.2/plotly.min.js",
    "https://unpkg.com/plotly.js-dist-min@2.35.2/plotly.min.js",
    "https://cdn.plot.ly/plotly-2.35.2.min.js",
]


@dataclass
class Hole:
    hole_id: str
    lon: float
    lat: float
    length_m: float | None = None
    elevation_m: float | None = None
    dip_deg: float | None = None      # -90 = straight down
    azimuth_deg: float | None = None  # degrees clockwise from north
    project: str = ""
    folder: Path | None = None        # NVCL hole folder (--data-dir only)
    has_log: bool = False
    log_name: str = ""
    intervals: pd.DataFrame | None = None  # depth_from, depth_to, group, confidence
    notes: list[str] = field(default_factory=list)
    collar: np.ndarray | None = None  # MGA easting, northing, elevation


def number(value: object) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def match_key(value: object) -> str:
    """Fold a hole name for joining, as files/site.py does. 'MPWD73 [chips]' -> 'mpwd73'."""
    text = re.sub(r"\[[^\]]*\]", " ", str(value or ""))
    return re.sub(r"[^a-z0-9]+", "", text.lower())


# --------------------------------------------------------------------------
# reading: NVCL hole folders
# --------------------------------------------------------------------------

def read_folder_holes(data_dir: Path) -> list[Hole]:
    holes = []
    for path in sorted(data_dir.glob("*/borehole.json")):
        meta = read_json(path)
        lon, lat = number(meta.get("x")), number(meta.get("y"))
        if lon is None or lat is None:
            continue
        holes.append(Hole(
            hole_id=str(meta.get("nvcl_id") or path.parent.name),
            lon=lon, lat=lat,
            length_m=number(meta.get("boreholeLength_m")),
            elevation_m=number(meta.get("elevation_m")),
            project=str(meta.get("project") or "").strip(),
            folder=path.parent,
            has_log=find_first(path.parent, GROUP_LOGS + SPECIES_LOGS) is not None,
        ))
    return holes


def read_folder_intervals(hole: Hole) -> pd.DataFrame | None:
    picked = pick_log(hole)
    if picked is None:
        return None
    path, rows = picked
    hole.log_name = path.stem.split("_", 1)[-1]  # '<uuid>_Grp1_sTSAS' -> 'Grp1_sTSAS'
    return metre_calls([(start, end, resolve_group(value)) for start, end, value in rows])


def pick_log(hole: Hole) -> tuple[Path, list] | None:
    """The copy of the preferred mineral log that belongs to this borehole.

    download.py puts every NVCL dataset's logs for a name into one scalars/
    folder, with nothing recording which dataset a file came from - and some
    names cover two different holes (data/raw/BH01 holds BH01_Behemoth,
    163-561 m, and a Bunbury bore logged 18-21.6 m). So never take sorted-glob
    order: take the copy whose logged span is closest to borehole.json's
    length (NVCL's scanned metres for the hole that file describes), then the
    one with the most calls.
    """
    for pattern in GROUP_LOGS + SPECIES_LOGS:
        copies = [(path, load_scalar_log(path)) for path in sorted((hole.folder / "scalars").glob(pattern))]
        copies = [(path, rows) for path, rows in copies if rows]
        if copies:
            return max(copies, key=lambda copy: log_fit(copy[1], hole.length_m))
    return None


def log_fit(rows: list, length_m: float | None) -> tuple[float, int]:
    span = max(end for _, end, _ in rows) - min(start for start, _, _ in rows)
    return (-abs(span - length_m) if length_m else 0.0, len(rows))


def metre_calls(rows: list[tuple[float, float, str]]) -> pd.DataFrame | None:
    """One dominant group per metre. confidence = that group's share of the
    metre's readings - the same "agreement" files/extract.py scores."""
    if not rows:
        return None
    samples = pd.DataFrame(rows, columns=["start", "end", "group"])
    samples["bin"] = np.floor((samples.start + samples.end) / 2 / BIN_M).astype(int)
    counts = samples.groupby(["bin", "group"]).size().rename("n").reset_index()
    counts["confidence"] = counts.n / counts.groupby("bin").n.transform("sum")
    top = counts.sort_values(["bin", "n"], ascending=[True, False]).drop_duplicates("bin")
    return pd.DataFrame({
        "depth_from": top.bin * BIN_M,
        "depth_to": (top.bin + 1) * BIN_M,
        "group": top.group,
        "confidence": top.confidence,
    }).reset_index(drop=True)


# --------------------------------------------------------------------------
# reading: the Docker Postgres (backend/holes/models.py tables)
# --------------------------------------------------------------------------

def db_connect(url: str | None):
    try:
        import psycopg
    except ImportError:
        sys.exit("--db needs psycopg: pip install -r backend/requirements.txt")
    if not url:
        env = dict(os.environ)
        try:
            from dotenv import dotenv_values
            env = {**dotenv_values(PROJECT_ROOT / ".env"), **env}
        except ImportError:
            pass
        # Same defaults as backend/hylogger/settings.py, except the port:
        # docker-compose.yml publishes Postgres on 5433.
        url = (f"host={env.get('POSTGRES_HOST', 'localhost')} port={env.get('POSTGRES_PORT', '5433')} "
               f"dbname={env.get('POSTGRES_DB', 'hylogger')} user={env.get('POSTGRES_USER', 'hylogger')} "
               f"password={env.get('POSTGRES_PASSWORD', 'hylogger')}")
    try:
        return psycopg.connect(url, connect_timeout=5)
    except psycopg.OperationalError as error:
        sys.exit(f"Couldn't reach Postgres - start it from team/ with `docker compose up -d`, "
                 f"or pass --db-url.\n{error}")


def read_db_holes(conn) -> list[Hole]:
    with conn.cursor() as cursor:
        cursor.execute("SELECT DISTINCT hole_id FROM measurements WHERE mineral_1 <> ''")
        logged = {row[0] for row in cursor.fetchall()}
        cursor.execute("SELECT hole_id, latitude, longitude, elevation_m, borehole_length_m, "
                       "inclination_deg, azimuth_deg FROM holes")
        rows = cursor.fetchall()
    return [
        Hole(hole_id=hole_id, lon=lon, lat=lat, elevation_m=number(elevation),
             length_m=number(length), dip_deg=number(dip), azimuth_deg=number(azimuth),
             has_log=hole_id in logged, log_name="measurements.mineral_1")
        for hole_id, lat, lon, elevation, length, dip, azimuth in rows
    ]


def read_db_intervals(conn, holes: list[Hole]) -> None:
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT hole_id, depth_from_m, depth_to_m, mineral_1, confidence FROM measurements "
            "WHERE hole_id = ANY(%s) AND mineral_1 <> '' ORDER BY hole_id, depth_from_m",
            ([hole.hole_id for hole in holes],),
        )
        table = pd.DataFrame(cursor.fetchall(),
                             columns=["hole_id", "depth_from", "depth_to", "group", "confidence"])
    for hole in holes:
        rows = table[table.hole_id == hole.hole_id].drop(columns="hole_id").reset_index(drop=True)
        hole.intervals = rows if len(rows) else None


# --------------------------------------------------------------------------
# collar catalog: dip, azimuth, elevation
# --------------------------------------------------------------------------

def read_collar_catalog(paths: list[Path]) -> dict[str, list[dict]]:
    """match_key(hole) -> every catalog row with that name, tables in priority order.
    Rows keep their lat/lon so fill_from_catalog can tell same-named holes apart."""
    catalog: dict[str, list[dict]] = {}
    for path in paths:
        if not path.is_file():
            continue
        if path.suffix.lower() == ".csv":
            table = pd.read_csv(path, encoding="utf-8-sig")
        else:
            table = pd.read_excel(path).rename(columns=CATALOG_COLUMNS)
        for row in table.to_dict("records"):
            key = match_key(row.get("hole_id"))
            if key and number(row.get("latitude")) is not None and number(row.get("longitude")) is not None:
                catalog.setdefault(key, []).append(row)
    return catalog


def fill_from_catalog(holes: list[Hole], catalog: dict[str, list[dict]]) -> None:
    """Fill each unknown field from the first catalog row, near this collar, that has it."""
    for hole in holes:
        rows = [row for row in catalog.get(match_key(hole.hole_id), [])
                if distance_km(hole, np.array([row["longitude"]]), np.array([row["latitude"]]))[0]
                <= CATALOG_MATCH_KM]

        def first(column: str) -> float | None:
            return next((value for value in (number(row.get(column)) for row in rows) if value is not None), None)

        hole.dip_deg = hole.dip_deg if hole.dip_deg is not None else first("inclination_deg")
        hole.azimuth_deg = hole.azimuth_deg if hole.azimuth_deg is not None else first("azimuth_deg")
        hole.elevation_m = hole.elevation_m if hole.elevation_m is not None else first("elevation_m")
        hole.length_m = max(hole.length_m or 0.0, first("borehole_length_m") or 0.0,
                            first("scanned_to_m") or 0.0) or None
        projects = [row["project"].strip() for row in rows if isinstance(row.get("project"), str)]
        hole.project = hole.project or next((project for project in projects if project), "")


# --------------------------------------------------------------------------
# picking which holes to draw
# --------------------------------------------------------------------------

def distance_km(hole: Hole, lons: np.ndarray, lats: np.ndarray) -> np.ndarray:
    """Great-circle distance from one collar to many, in km."""
    lat1, lon1 = math.radians(hole.lat), math.radians(hole.lon)
    lat2, lon2 = np.radians(lats), np.radians(lons)
    h = np.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * np.arcsin(np.sqrt(h))


def cluster_score(group: list[Hole]) -> tuple[float, int]:
    """Logged metres first, so a pad of 3 m engineering holes never beats a real drill pattern."""
    return sum(hole.length_m or 0 for hole in group if hole.has_log), len(group)


def find_clusters(holes: list[Hole], radius_km: float) -> list[list[Hole]]:
    """Single-linkage groups - two collars closer than radius_km share a group. Best first."""
    lons = np.array([hole.lon for hole in holes])
    lats = np.array([hole.lat for hole in holes])
    parent = list(range(len(holes)))

    def root(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, hole in enumerate(holes):
        for j in np.nonzero(distance_km(hole, lons, lats) < radius_km)[0]:
            parent[root(int(j))] = root(i)
    groups: dict[int, list[Hole]] = {}
    for i, hole in enumerate(holes):
        groups.setdefault(root(i), []).append(hole)
    return sorted(groups.values(), key=cluster_score, reverse=True)


def print_clusters(holes: list[Hole], radius_km: float, top: int = 10) -> None:
    print(f"Biggest groups of holes within {radius_km:g} km of each other, by logged metres:\n")
    for rank, group in enumerate(find_clusters(holes, radius_km)[:top], 1):
        logged = sum(hole.has_log for hole in group)
        projects = Counter(hole.project for hole in group if hole.project).most_common(1)
        names = ", ".join(hole.hole_id for hole in group[:6]) + (" ..." if len(group) > 6 else "")
        print(f"{rank:>3}. {len(group):>3} holes, {logged:>3} logged, {cluster_score(group)[0]:>8,.0f} m"
              f"  {projects[0][0] if projects else '':<22.22}  {names}")
    print("\nDraw one with:  python holes_3d.py [--data-dir ...] --near <hole id>")


def select_holes(holes: list[Hole], args: argparse.Namespace) -> list[Hole]:
    by_key = {match_key(hole.hole_id): hole for hole in holes}
    if args.holes:
        missing = [name for name in args.holes if match_key(name) not in by_key]
        if missing:
            sys.exit(f"Not in this dataset: {', '.join(missing)} (try --list-clusters)")
        chosen = [by_key[match_key(name)] for name in args.holes]
    elif args.near:
        centre = by_key.get(match_key(args.near))
        if centre is None:
            sys.exit(f"Not in this dataset: {args.near} (try --list-clusters)")
        lons = np.array([hole.lon for hole in holes])
        lats = np.array([hole.lat for hole in holes])
        distances = distance_km(centre, lons, lats)
        order = np.argsort(distances)
        chosen = [holes[i] for i in order if distances[i] <= args.radius_km]
    else:
        chosen = find_clusters(holes, args.radius_km)[0]
    if len(chosen) > args.max_holes:
        print(f"{len(chosen)} holes match; drawing the first {args.max_holes} (raise --max-holes for more)")
        chosen = chosen[:args.max_holes]
    return chosen


# --------------------------------------------------------------------------
# geometry
# --------------------------------------------------------------------------

def place_holes(holes: list[Hole]) -> tuple[int, bool]:
    """Collars -> MGA metres. Returns (MGA zone, whether any real elevation was known)."""
    zone = int((np.mean([hole.lon for hole in holes]) + 180) // 6) + 1
    to_mga = Transformer.from_crs("EPSG:4326", f"EPSG:{28300 + zone}", always_xy=True)
    known = [hole.elevation_m for hole in holes if hole.elevation_m]  # None and 0 both mean unknown
    level = float(np.median(known)) if known else 0.0
    for hole in holes:
        if not hole.elevation_m:
            hole.notes.append(f"elevation unknown, drawn at {level:.0f} m" if known else "elevation unknown")
            hole.elevation_m = level
        if hole.dip_deg is None:
            hole.notes.append("dip unknown, drawn vertical")
            hole.dip_deg = -90.0
        if hole.azimuth_deg is None:
            if abs(hole.dip_deg) < 89.5:
                hole.notes.append("azimuth unknown, drawn to the north")
            hole.azimuth_deg = 0.0
        logged_to = float(hole.intervals.depth_to.max()) if hole.intervals is not None else 0.0
        hole.length_m = max(hole.length_m or 0.0, logged_to) or 1.0
        east, north = to_mga.transform(hole.lon, hole.lat)
        hole.collar = np.array([east, north, hole.elevation_m])
    return zone, bool(known)


def along_hole(hole: Hole, depths) -> np.ndarray:
    """Straight-line (tangent) desurvey - the same maths as backend/holes/geo.py.
    Swap in minimum curvature here if downhole survey stations turn up."""
    dip, azimuth = math.radians(abs(hole.dip_deg)), math.radians(hole.azimuth_deg)
    depths = np.asarray(depths, dtype=float)
    horizontal = depths * math.cos(dip)
    offset = np.column_stack([horizontal * math.sin(azimuth),
                              horizontal * math.cos(azimuth),
                              -depths * math.sin(dip)])
    return hole.collar + offset


def runs(intervals: pd.DataFrame) -> pd.DataFrame:
    """Merge touching metres with the same call into one run - fewer, longer tubes."""
    shown = intervals.assign(group=np.where(intervals.confidence < CONFIDENCE_THRESHOLD,
                                            UNCERTAIN, intervals.group))
    starts = (shown.group != shown.group.shift()) | (shown.depth_from > shown.depth_to.shift() + 1e-6)
    merged = shown.groupby(starts.cumsum()).agg(
        depth_from=("depth_from", "min"), depth_to=("depth_to", "max"),
        group=("group", "first"), confidence=("confidence", "mean"),
    )
    return merged[merged.depth_to > merged.depth_from].reset_index(drop=True)


def tube(starts: np.ndarray, ends: np.ndarray, radius: float, sides: int = TUBE_SIDES):
    """Vertices and triangle indices for straight tube segments starts[n] -> ends[n]."""
    axis = ends - starts
    axis /= np.linalg.norm(axis, axis=1, keepdims=True)
    helper = np.where(np.abs(axis[:, 2:3]) < 0.9, [[0.0, 0.0, 1.0]], [[1.0, 0.0, 0.0]])
    u = np.cross(axis, helper)
    u /= np.linalg.norm(u, axis=1, keepdims=True)
    v = np.cross(axis, u)
    angle = np.linspace(0, 2 * np.pi, sides, endpoint=False)[None, :, None]
    ring = radius * (np.cos(angle) * u[:, None, :] + np.sin(angle) * v[:, None, :])
    vertices = np.concatenate([starts[:, None, :] + ring, ends[:, None, :] + ring], axis=1).reshape(-1, 3)
    k = np.arange(sides)
    base = (np.arange(len(starts)) * 2 * sides)[:, None]
    a, b = base + k, base + (k + 1) % sides
    c, d = a + sides, b + sides
    return (vertices, np.concatenate([a, a], 1).ravel(),
            np.concatenate([b, d], 1).ravel(), np.concatenate([d, c], 1).ravel())


def spans_an_area(xy: np.ndarray) -> bool:
    """At least three collars, and not all on one line - enough to triangulate between."""
    return len(xy) >= 3 and np.linalg.matrix_rank(xy - xy.mean(axis=0), tol=1.0) == 2


def ground_model(holes: list[Hole]):
    """RL of the collar surface at any (x, y): linear between collars, nearest outside them."""
    xy = np.array([hole.collar[:2] for hole in holes])
    z = np.array([hole.collar[2] for hole in holes])
    if spans_an_area(xy):
        def at(points: np.ndarray) -> np.ndarray:
            linear = griddata(xy, z, points, method="linear")
            return np.where(np.isnan(linear), griddata(xy, z, points, method="nearest"), linear)
        return at
    level = float(z.mean())
    return lambda points: np.full(len(points), level)


def default_model_range(holes: list[Hole]) -> float:
    """How far a --model domain may reach from a hole: a bit over the typical collar
    spacing, so an intercept can join up with the same rock in the next hole but
    never reaches across two holes' worth of undrilled ground."""
    xy = np.array([hole.collar[:2] for hole in holes])
    if len(xy) < 2:
        return 50.0
    spacing = float(np.median(cKDTree(xy).query(xy, k=2)[0][:, 1]))
    return float(np.clip(1.25 * spacing, 25.0, 400.0))


# --------------------------------------------------------------------------
# plotly traces
# --------------------------------------------------------------------------

def rounded(values, digits: int = 1) -> list:
    return np.round(np.asarray(values, dtype=float), digits).tolist()


def group_colours(holes: list[Hole]) -> dict[str, str]:
    groups = sorted({group for hole in holes if hole.intervals is not None
                     for group in hole.intervals.group})
    extra = iter(EXTRA_COLOURS * 4)
    colours = {group: MINERAL_COLOURS.get(group) or next(extra) for group in groups}
    colours[UNCERTAIN] = UNCERTAIN_COLOUR
    return colours


def interval_traces(holes: list[Hole], colours: dict[str, str], radius: float) -> list[dict]:
    """One mesh per mineral group across every hole, so the legend toggles a group everywhere."""
    segments: dict[str, dict[str, list]] = {}
    for hole in holes:
        if hole.intervals is None:
            continue
        table = runs(hole.intervals)
        starts, ends = along_hole(hole, table.depth_from), along_hole(hole, table.depth_to)
        for n, row in enumerate(table.itertuples(index=False)):
            part = segments.setdefault(row.group, {"starts": [], "ends": [], "text": [], "metres": 0.0})
            part["starts"].append(starts[n])
            part["ends"].append(ends[n])
            part["metres"] += row.depth_to - row.depth_from
            part["text"].append(f"<b>{hole.hole_id}</b><br>{row.depth_from:g}–{row.depth_to:g} m<br>"
                                f"{row.group}<br>{row.confidence:.0%} of readings agree")

    order = sorted((group for group in segments if group != UNCERTAIN),
                   key=lambda group: -segments[group]["metres"])
    if UNCERTAIN in segments:
        order.append(UNCERTAIN)

    traces = []
    for group in order:
        part = segments[group]
        vertices, i, j, k = tube(np.array(part["starts"]), np.array(part["ends"]),
                                 radius * (0.5 if group == UNCERTAIN else 1.0))
        label = f"{group} (under {CONFIDENCE_THRESHOLD:.0%} agree)" if group == UNCERTAIN else group
        traces.append({
            "type": "mesh3d", "name": f"{label} · {part['metres']:,.0f} m",
            "x": rounded(vertices[:, 0]), "y": rounded(vertices[:, 1]), "z": rounded(vertices[:, 2]),
            "i": i.tolist(), "j": j.tolist(), "k": k.tolist(),
            "color": colours[group], "flatshading": False,
            "lighting": LIGHTING, "lightposition": LIGHT_POSITION,
            "text": np.repeat(part["text"], 2 * TUBE_SIDES).tolist(),
            "hovertemplate": "%{text}<extra></extra>", "showlegend": True,
        })
    return traces


def hole_line_trace(holes: list[Hole], theme: dict) -> dict:
    """The full hole, collar to end - what's left visible is the unlogged core."""
    x, y, z, text = [], [], [], []
    for hole in holes:
        ends = along_hole(hole, [0.0, hole.length_m])
        x += [*rounded(ends[:, 0]), None]
        y += [*rounded(ends[:, 1]), None]
        z += [*rounded(ends[:, 2]), None]
        text += [hole.hole_id, hole.hole_id, None]
    return {"type": "scatter3d", "mode": "lines", "name": "Drill hole (not logged)",
            "x": x, "y": y, "z": z, "text": text, "hovertemplate": "%{text}<extra></extra>",
            "line": {"color": theme["trace"], "width": 3}}


def collar_trace(holes: list[Hole], theme: dict, lift: float) -> dict:
    hover = []
    for hole in holes:
        east, north, rl = hole.collar
        lines = [f"<b>{hole.hole_id}</b>", f"{hole.length_m:,.1f} m, dip {hole.dip_deg:+.0f}° "
                 f"toward {hole.azimuth_deg:03.0f}°", f"E {east:,.0f}  N {north:,.0f}  RL {rl:,.0f}"]
        if hole.project:
            lines.append(hole.project)
        hover.append("<br>".join(lines + [f"<i>{note}</i>" for note in hole.notes]))
    return {"type": "scatter3d", "mode": "markers+text", "name": "Collars",
            "x": rounded([hole.collar[0] for hole in holes]),
            "y": rounded([hole.collar[1] for hole in holes]),
            "z": rounded([hole.collar[2] + lift for hole in holes]),
            "text": [hole.hole_id for hole in holes], "textposition": "top center",
            "textfont": {"size": 11, "color": theme["fg"]},
            "marker": {"size": 4, "color": theme["fg"], "symbol": "diamond"},
            "hovertext": hover, "hovertemplate": "%{hovertext}<extra></extra>"}


def surface_trace(holes: list[Hole], lo: np.ndarray, hi: np.ndarray, elevation_known: bool) -> dict:
    """A sheet through the collars, only where there are collars on every side of it -
    extrapolating past the outermost holes would just be inventing topography.
    Fewer than three collars (or all in a line) get a flat sheet at their mean RL."""
    xy = np.array([hole.collar[:2] for hole in holes])
    z = np.array([hole.collar[2] for hole in holes])
    n = 48
    gx, gy = np.meshgrid(np.linspace(lo[0], hi[0], n), np.linspace(lo[1], hi[1], n))
    if spans_an_area(xy):
        gz = griddata(xy, z, (gx, gy), method="linear").ravel()  # NaN outside the collars
        name = ("Surface through collar RLs (interpolated)" if elevation_known
                else "Collar level (real RLs unknown)")
    else:
        gz = np.full(n * n, z.mean())
        name = "Collar level (too few holes for a surface)"
    index = np.arange(n * n).reshape(n, n)
    a, b = index[:-1, :-1].ravel(), index[:-1, 1:].ravel()
    c, d = index[1:, :-1].ravel(), index[1:, 1:].ravel()
    triangles = np.column_stack([np.concatenate([a, b]), np.concatenate([b, d]), np.concatenate([c, c])])
    triangles = triangles[np.isfinite(gz[triangles]).all(axis=1)]
    return {"type": "mesh3d", "name": name,
            "x": rounded(gx.ravel()), "y": rounded(gy.ravel()), "z": rounded(np.nan_to_num(gz, nan=z.mean())),
            "i": triangles[:, 0].tolist(), "j": triangles[:, 1].tolist(), "k": triangles[:, 2].tolist(),
            "color": SURFACE_COLOUR, "opacity": 0.25, "flatshading": False,
            "lighting": LIGHTING, "lightposition": LIGHT_POSITION, "hoverinfo": "skip", "showlegend": True}


def domain_trace(holes: list[Hole], group: str, colour: str, lo: np.ndarray, hi: np.ndarray,
                 ground, range_m: float) -> dict | None:
    """Interpolate "how much of this rock is <group>" between the holes and draw where it's over half.

    Each 5 m composite of confidently logged core gives the share of its metres
    that are <group>; a linear RBF (the kernel Leapfrog's default interpolant
    uses) spreads that share through a 3D grid, and the isosurface at 0.5 is
    the domain boundary. Grid cells further than range_m from any composite,
    or above the collar surface, are forced to 0 so the solid never runs off
    into ground nobody drilled.
    """
    points, values = [], []
    for hole in holes:
        if hole.intervals is None:
            continue
        sure = hole.intervals[hole.intervals.confidence >= CONFIDENCE_THRESHOLD]
        if sure.empty:
            continue
        share = (sure.group == group).groupby(np.floor(sure.depth_from / COMPOSITE_M)).mean()
        points.append(along_hole(hole, (share.index.to_numpy() + 0.5) * COMPOSITE_M))
        values.append(share.to_numpy(dtype=float))
    if not points or max(value.max() for value in values) < 0.5:
        print(f"  --model {group}: no {COMPOSITE_M:g} m composite is mostly {group}, nothing to draw")
        return None
    points, keep = np.unique(np.round(np.vstack(points), 2), axis=0, return_index=True)
    values = np.concatenate(values)[keep]

    rbf = RBFInterpolator(points, values, kernel="linear",
                          neighbors=None if len(points) <= 3000 else 300)
    size = hi - lo
    counts = np.maximum(8, np.round(size / size.max() * GRID_CELLS).astype(int))
    axes = [np.linspace(lo[axis], hi[axis], counts[axis]) for axis in range(3)]
    grid = np.column_stack([mesh.ravel() for mesh in np.meshgrid(*axes, indexing="ij")])
    estimate = rbf(grid)
    estimate[cKDTree(points).query(grid)[0] > range_m] = 0.0
    estimate[grid[:, 2] > ground(grid[:, :2])] = 0.0
    # Zero the grid's outer shell too, so a domain that runs into the edge of the
    # scene is closed off as a solid instead of left as an open sheet.
    shell = estimate.reshape(tuple(counts))
    shell[[0, -1], :, :] = shell[:, [0, -1], :] = shell[:, :, [0, -1]] = 0.0
    if estimate.max() < 0.5:
        print(f"  --model {group}: interpolated share never reaches 50%, nothing to draw")
        return None
    return {"type": "isosurface", "name": f"{group} domain (interpolated, ≤{range_m:.0f} m from holes)",
            "x": rounded(grid[:, 0]), "y": rounded(grid[:, 1]), "z": rounded(grid[:, 2]),
            "value": rounded(estimate, 3), "isomin": 0.5, "isomax": float(max(estimate.max(), 0.5)),
            "surface": {"count": 1}, "caps": {axis: {"show": False} for axis in "xyz"},
            "colorscale": [[0, colour], [1, colour]], "showscale": False, "opacity": 0.4,
            "lighting": LIGHTING, "lightposition": LIGHT_POSITION, "hoverinfo": "skip", "showlegend": True}


# --------------------------------------------------------------------------
# page
# --------------------------------------------------------------------------

def camera(azimuth_deg: float, plunge_deg: float, aspect: np.ndarray) -> dict:
    """Look toward azimuth_deg, tilted down by plunge_deg - Leapfrog's "Plunge +25 Azimuth 030".
    Flat scenes (a wide pattern of shallow holes) get the camera closer so they fill the frame."""
    distance = 1.6 + 0.5 * max(float(aspect[2]), 0.2)
    azimuth, plunge = math.radians(azimuth_deg), math.radians(plunge_deg)
    look = np.array([math.sin(azimuth) * math.cos(plunge), math.cos(azimuth) * math.cos(plunge),
                     -math.sin(plunge)])
    eye = -look * distance
    return {"eye": dict(zip("xyz", np.round(eye, 3).tolist())),
            "up": {"x": 0, "y": 0, "z": 1}, "center": {"x": 0, "y": 0, "z": 0}}


def build_figure(holes: list[Hole], zone: int, elevation_known: bool, title: str,
                 args: argparse.Namespace) -> dict:
    theme = THEMES["dark" if args.dark else "light"]
    ends = np.vstack([along_hole(hole, [0.0, hole.length_m]) for hole in holes])
    lo, hi = ends.min(axis=0), ends.max(axis=0)
    pad = max(10.0, 0.08 * float((hi - lo)[:2].max()))
    lo, hi = lo - [pad, pad, pad / 2], hi + [pad, pad, pad / 2]
    radius = args.tube_radius or float(np.clip(0.006 * (hi - lo).max(), 0.5, 25.0))

    colours = group_colours(holes)
    ground = ground_model(holes)
    data = [surface_trace(holes, lo, hi, elevation_known)]
    data += interval_traces(holes, colours, radius)
    data += [hole_line_trace(holes, theme), collar_trace(holes, theme, lift=radius * 2)]

    range_m = args.model_range or default_model_range(holes)
    for group in [group.upper() for group in args.model or []]:
        if group not in colours or group == UNCERTAIN:
            logged = ", ".join(sorted(set(colours) - {UNCERTAIN}))
            print(f"  --model {group}: not logged in these holes (have: {logged})")
            continue
        trace = domain_trace(holes, group, colours[group], lo, hi, ground, range_m)
        if trace:
            data.append(trace)

    size = (hi - lo) * [1.0, 1.0, args.vertical_exaggeration]
    aspect = size / size.max()

    def axis(label: str, low: float, high: float) -> dict:
        return {"title": {"text": label}, "range": [low, high], "tickformat": ",.0f",
                "showbackground": True, "backgroundcolor": theme["wall"], "gridcolor": theme["grid"],
                "zerolinecolor": theme["grid"], "color": theme["fg"], "showspikes": False}

    logs = sorted({hole.log_name for hole in holes if hole.intervals is not None})
    footer = (f"View: plunge {args.view_plunge:+.0f}°, azimuth {args.view_azimuth:03.0f}°"
              f" · vertical exaggeration {args.vertical_exaggeration:g}×<br>"
              f"Tube colour = dominant mineral group per metre ({', '.join(logs) or 'no logs'}). "
              f"Thin grey = under {CONFIDENCE_THRESHOLD:.0%} of readings agree.<br>"
              "Surfaces and domains are interpolated between holes - interpretation, not observation.")
    z_label = "Elevation (m)" if elevation_known else "Elevation (m, relative - collar RLs unknown)"
    layout = {
        "title": {"text": title, "x": 0.01, "xanchor": "left", "font": {"size": 16}},
        "paper_bgcolor": theme["bg"],
        "font": {"color": theme["fg"], "family": "system-ui, -apple-system, 'Segoe UI', sans-serif"},
        "margin": {"l": 0, "r": 0, "t": 44, "b": 0},
        "legend": {"title": {"text": "Down-hole mineral group"}, "x": 0.01, "y": 0.94,
                   "bgcolor": theme["legend"], "itemsizing": "constant"},
        "scene": {
            "xaxis": axis(f"Easting (m, MGA zone {zone})", lo[0], hi[0]),
            "yaxis": axis("Northing (m)", lo[1], hi[1]),
            "zaxis": axis(z_label, lo[2], hi[2]),
            "aspectmode": "manual", "aspectratio": dict(zip("xyz", np.round(aspect, 4).tolist())),
            "camera": camera(args.view_azimuth, args.view_plunge, aspect), "bgcolor": theme["bg"],
        },
        "annotations": [{"text": footer, "xref": "paper", "yref": "paper", "x": 0.99, "y": 0.01,
                         "xanchor": "right", "yanchor": "bottom", "align": "right", "showarrow": False,
                         "font": {"size": 11, "color": theme["muted"]}}],
    }
    config = {"displaylogo": False, "responsive": True, "scrollZoom": True,
              "toImageButtonOptions": {"format": "png", "scale": 2}}
    return {"data": data, "layout": layout, "config": config}


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{title}}</title>
<style>
  html, body { margin: 0; height: 100%; background: {{bg}}; }
  #plot { position: fixed; inset: 0; }
  #offline { padding: 24px; font: 15px system-ui, sans-serif; color: #b42318; }
</style>
{{library}}
</head>
<body>
<div id="plot"></div>
<script>
  const figure = {{figure}};
  const sources = {{sources}};

  function draw() {
    Plotly.newPlot("plot", figure.data, figure.layout, figure.config);
  }

  // Use the embedded plotly.js if there is one, else the first CDN that loads.
  function load(next) {
    if (window.Plotly) return draw();
    if (next >= sources.length) {
      document.body.innerHTML = '<p id="offline">Couldn\\'t load plotly.js from any CDN. ' +
        'Open this page with internet access, or run <code>pip install plotly</code> and ' +
        're-run holes_3d.py - it then embeds plotly.js so the page works offline.</p>';
      return;
    }
    const script = document.createElement("script");
    script.src = sources[next];
    script.onload = draw;
    script.onerror = () => load(next + 1);
    document.head.appendChild(script);
  }
  load(0);
</script>
</body>
</html>
"""


def write_page(figure: dict, title: str, dark: bool, out: Path) -> Path:
    try:
        from plotly.offline import get_plotlyjs  # optional - embeds plotly.js for offline use
        library = f"<script>{get_plotlyjs()}</script>"
    except ImportError:
        library = ""
    figure["config"]["toImageButtonOptions"]["filename"] = out.stem
    payload = json.dumps(figure, separators=(",", ":")).replace("</", "<\\/")
    page = (PAGE.replace("{{title}}", html.escape(title))
                .replace("{{bg}}", THEMES["dark" if dark else "light"]["bg"])
                .replace("{{library}}", library)
                .replace("{{sources}}", json.dumps(PLOTLY_SOURCES))
                .replace("{{figure}}", payload))
    return atomic_write_text(out, page)


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--data-dir", type=Path,
                        help="folder of NVCL hole folders (default: ../database5553/etl4, else data/raw)")
    source.add_argument("--db", action="store_true",
                        help="read the holes + measurements tables from the Docker Postgres instead")
    parser.add_argument("--db-url", help="libpq connection string (default: .env POSTGRES_*, localhost:5433)")

    pick = parser.add_mutually_exclusive_group()
    pick.add_argument("--holes", nargs="+", metavar="ID", help="draw exactly these holes")
    pick.add_argument("--near", metavar="ID", help="draw this hole and every hole within --radius-km")
    parser.add_argument("--radius-km", type=float, default=3.0,
                        help="how close collars must be to count as one group (default 3)")
    parser.add_argument("--max-holes", type=int, default=40)
    parser.add_argument("--list-clusters", action="store_true", help="list the biggest groups of holes and stop")

    parser.add_argument("--model", nargs="+", metavar="GROUP",
                        help="interpolate these mineral groups into 3D domains, e.g. --model CHLORITE")
    parser.add_argument("--model-range", type=float, metavar="M",
                        help="max distance a domain reaches from a hole (default: from the hole spacing)")
    parser.add_argument("--vertical-exaggeration", type=float, default=1.0)
    parser.add_argument("--view-azimuth", type=float, default=30.0, help="compass direction to look toward")
    parser.add_argument("--view-plunge", type=float, default=25.0, help="degrees to look down")
    parser.add_argument("--tube-radius", type=float, metavar="M", help="default scales with the scene")
    parser.add_argument("--dark", action="store_true", help="black background")
    parser.add_argument("--out", type=Path, help=f"HTML file to write (default: {OUTPUT_DIR.relative_to(PROJECT_ROOT)}/<name>.html)")
    parser.add_argument("--no-open", action="store_true", help="don't open the page in a browser")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    conn = None
    if args.db:
        conn = db_connect(args.db_url)
        holes, source = read_db_holes(conn), "the Postgres holes table"
    else:
        data_dir = args.data_dir or next((path for path in DEFAULT_DATA_DIRS if path.is_dir()), None)
        if data_dir is None:
            sys.exit(f"No data folder found - pass --data-dir (looked in {', '.join(map(str, DEFAULT_DATA_DIRS))})")
        if not data_dir.is_dir():
            sys.exit(f"No such folder: {data_dir}")
        holes, source = read_folder_holes(data_dir), str(data_dir)
    if not holes:
        sys.exit(f"No holes with a collar position in {source}")
    print(f"{len(holes)} holes in {source}")

    if args.list_clusters:
        print_clusters(holes, args.radius_km)
        return

    chosen = select_holes(holes, args)
    if conn is not None:
        read_db_intervals(conn, chosen)
        conn.close()
    else:
        for hole in chosen:
            hole.intervals = read_folder_intervals(hole)
    fill_from_catalog(chosen, read_collar_catalog(COLLAR_TABLES))
    zone, elevation_known = place_holes(chosen)

    projects = Counter(hole.project for hole in chosen if hole.project).most_common(1)
    name = projects[0][0] if projects else f"Around {chosen[0].hole_id}"
    title = f"{name} · {len(chosen)} hole{'s' * (len(chosen) != 1)} · GDA94 / MGA zone {zone}"

    print(f"\n{title}")
    for hole in chosen:
        logged = (f"logged {hole.intervals.depth_from.min():g}–{hole.intervals.depth_to.max():g} m "
                  f"({hole.log_name})" if hole.intervals is not None else "no mineral log")
        notes = f"  [{'; '.join(hole.notes)}]" if hole.notes else ""
        print(f"  {hole.hole_id:<16} {hole.length_m:>7.1f} m  dip {hole.dip_deg:+5.0f}° "
              f"toward {hole.azimuth_deg:03.0f}°  RL {hole.elevation_m:6.0f}  {logged}{notes}")

    figure = build_figure(chosen, zone, elevation_known, title, args)
    suffix = "".join(f"_{group.lower()}" for group in args.model or [])
    out = args.out or OUTPUT_DIR / f"{safe_name(name, 'holes')}{suffix}{'_dark' if args.dark else ''}.html"
    write_page(figure, title, args.dark, out)
    print(f"\n-> {out}")
    if not args.no_open:
        webbrowser.open(out.resolve().as_uri())


if __name__ == "__main__":
    main()
