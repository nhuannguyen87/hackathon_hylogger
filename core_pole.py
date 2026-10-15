#!/usr/bin/env python
"""Slices GSWA HyLogger tray photos into their rows of core, stacks every row
of a hole into one depth-true "core pole", and pins it to the hole's collar
from the GSWA HyLogger catalog - for the zipped TSG packages the catalog's
download links give (../data5553/<HOLE>/: <HOLE>_0001.jpg ... plus
<HOLE>_tsg.tsg/.bip), not the NVCL web-service downloads core_strip.py reads.

Why not core_strip.py on these photos: it finds rows from pixel brightness,
and on GSWA package photos that locks onto the tray, not the core - 3 thin
slivers of teal rail for GDD005 tray 1's 4 rows, 1 "row" for tray 20, five
33 px slivers for tray 21's ~200 px rows (checked 2026-09-28) - and it
splits a tray's depth evenly across its rows. Neither is needed here,
because the package already says where everything is:

  - The TSG scalars give, for every 8 mm scan sample, its Tray, Section
    (= row), SecDist (mm along the row) and Depth (m) - the HyLogger's own
    depth, already tied to the driller's core blocks (TIDL). Along core,
    depth advances with SecDist; over a wooden block, a spacer or empty
    channel it holds still. So which rows a tray has, where the core starts
    and stops along each one, and the depth of every millimetre of it come
    from the package, not from guessing at pixels.
  - The tray photo is TSG's own render of those sections: a black title bar,
    a white axis line at SecDist 0 with ticks along the bottom (every 50 mm,
    or 10 mm on some renders), and the tray's sections stacked top-to-bottom
    as equal-height bands at the same px/mm as the axis (GDD005 tray 1: 4
    bands x 85.13 mm x 2.998 px/mm = 1,021 px, the plot's measured height).
    So a row's pixel box is computed from the axis, not detected. When the
    package has its linescan (<HOLE>_tsg_cras.bip) its section table - read
    header-only, not the multi-GB imagery - cross-checks every band's width.

Depth-true: each row is resampled so pixel y is linear in depth, at one
scale for the whole hole (PX_PER_MM, both axes, so the HQ->NQ step in core
diameter shows). Blocks and spacers take no depth, so they drop out and their
depths are kept as `markers`; core loss the HyLogger spread through a run
stretches that run a little (GDD005: median 0.96 m of depth per m of core,
95% of rows within 0.85-1.04); depth with no imaged core at all - pre-collar,
between trays, lost core - stays blank and is listed in `gaps`, never closed
up. Pixel y then *is* depth, so the 3D pole, the mineral strip and any log
beside it line up.

Output per hole, in core_strip.py's layout so /api/holes/<id>/core-strip/,
CoreStripPanel, Hole3D and HoleMap's photo poles show it unchanged:
  data/media/core_strips/<hole>/
    sheet_N.jpg             SHEET_M metres of core each, depth down the page,
                            sheet edges on whole multiples of SHEET_M
    tsg_sheet_N.png         the TSA mineral group of every scan sample,
                            pixel-aligned to sheet_N.jpg
    overview.jpg            the whole hole on one page, for a look/QA
    depth_pixel_table.json  rows, gaps, block markers, the collar (catalog
                            match, GDA2020/MGA2020, dip/azimuth, trace), QA
                            checks and the source files' SHA-256
    qa/tray_NNNN.jpg        with --qa-images: each tray with the cut drawn on
  data/media/core_strips/poles.geojson   every pole's collar, for the map

Collars come from the GSWA catalog (hylogger_ver1/collars.xlsx), matched on
the UWI in the TSG header when it has one - hole names collide (BH01 is two
holes 1,250 km apart) - else on the name, and a name match further than
SAME_HOLE_KM from the header's own lat/lon is refused. The catalog's datum
(mostly GDA94, some AGD84/WGS84) is transformed to GDA2020 with pyproj. A
missing elevation stays missing and is flagged, not set to 0.

Usage:
    python core_pole.py --hole GDD005
    python core_pole.py --hole GDD005 --hole KD1 --qa-images
    python core_pole.py --all                  # every package under --packages
"""

from __future__ import annotations

import argparse
import math
import re
import struct
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import atomic_write_json, read_json, sha256_file, utc_now  # noqa: E402
from mineral_strip import BLANK, MINERAL_COLOURS, UNKNOWN_COLOUR, hex_to_rgb, resolve_group  # noqa: E402
from nvcl_datasets import SAME_HOLE_KM, distance_km  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent
PACKAGES_DIR = PROJECT_ROOT.parent / "data5553"
CATALOG_PATH = PACKAGES_DIR / "hylogger_ver1" / "collars.xlsx"
OUTPUT_DIR = PROJECT_ROOT / "data" / "media" / "core_strips"

TRAY_PHOTO = re.compile(r"^(?P<hole>.+)_(?P<tray>\d{4})\.jpe?g$", re.IGNORECASE)

PX_PER_MM = 2.0             # output scale, both axes; the package photos are ~3 px/mm
SHEET_M = 10.0              # metres of depth per sheet (2 px/mm -> 20,000 px, core_strip.py's cap)
NICE_TICKS_MM = (5.0, 10.0, 20.0, 25.0, 50.0, 100.0)  # x-axis tick spacings TSG renders use
NON_BLACK = 30              # brightest channel above this = photo or axis, not black chrome
PLOT_FILL = 0.5             # share of a pixel row/column that must be non-black to be in the plot
MIN_CORE_MM = 10.0          # a row with less core than this along it is a stray sample, not core
JUMP_M = 0.05               # one ~8 mm scan step advancing more depth than this = logged lost core
LOW_RECOVERY = 1.3          # m of depth per m of core above which a row is flagged as stretched
GAP_REPORT_M = 0.01         # depth with no imaged core longer than this is listed in "gaps"
BAND_TOLERANCE = 0.03       # photo band width vs the linescan's section width, fractional
NO_CORE_RGB = (36, 36, 40)  # depth with no imaged core: pre-collar, lost core, between trays

OVERVIEW_PX_PER_M = 40      # overview.jpg is squashed: 40 px per metre down, fixed width across
OVERVIEW_COLUMN_M = 25.0
OVERVIEW_PHOTO_W = 34
OVERVIEW_MINERAL_W = 10

# TSA group columns, SWIR first - mineral_strip.py's GROUP_LOG_GLOBS order.
GROUP_COLUMNS = ("Grp1 sTSAS", "Grp1 uTSAS", "Grp1 sTSAV", "Grp1 uTSAV", "Grp1 sjCLST", "Grp1 ujCLST")
# BLANK plus the "this wasn't rock" classes tsg_bridge.NOT_A_MINERAL lists
# (calibration targets, tray plastic, explicit non-calls), upper-cased.
NOT_ROCK = BLANK | {
    "DEFAULT", "NOTINLIBRARY", "DARK", "NOISY", "HIGHERROR", "MASKEDOFF", "VEGETATION-DRY",
    "VEGETATION-GREEN", "ISAWHITE", "ISAYELLOW", "PLASTICCHIPTRAY", "TEFLON", "YELLOWMARKER",
    "GALVANISEDIRON", "ODZINCALUME",
}

# GSWA catalog "Original Datum" -> geographic CRS; MGA/AMG grids by zone below.
DATUM_EPSG = {"GDA2020": 7844, "GDA94": 4283, "WGS84": 4326, "AGD84": 4203, "AGD66": 4202}
GRID_EPSG_BASE = {"GDA2020": 7800, "GDA94": 28300, "AGD84": 20300, "AGD66": 20200}


# --------------------------------------------------------------------------
# the TSG package
# --------------------------------------------------------------------------

@dataclass
class Section:
    """One TSG section: one row of core in one tray photo."""
    tray: int
    number: int              # TSG's hole-wide section number
    secdist: np.ndarray      # mm along the row, per scan sample
    depth: np.ndarray        # m, TSG's TIDL-corrected depth per sample
    groups: list             # TSA mineral group per sample, None where masked/no call
    markers: list            # [(secdist_mm, depth_m)] depths typed in at core blocks

    def core(self) -> np.ndarray:
        """[[d0, d1, x0, x1], ...]: the sample-to-sample steps where depth
        advances, i.e. where this row is core. A step where depth holds still
        (block, spacer, empty channel) isn't core and isn't here."""
        advances = np.diff(self.depth) > 1e-9
        return np.column_stack([self.depth[:-1][advances], self.depth[1:][advances],
                                self.secdist[:-1][advances], self.secdist[1:][advances]])

    def core_pieces(self) -> list[np.ndarray]:
        """core() split wherever one scan step jumps more than JUMP_M of depth -
        how TSG logs lost core inside a row. Stretching the photo across a
        jump like that smears a centimetre of core over metres (KD1 tray 27
        row 6: 6.38 m in one 8 mm step), so it's left as a gap instead. Core
        loss the HyLogger spread evenly through a run is not a jump and stays
        a (flagged) stretch - that is the depth the spectra are keyed to."""
        core = self.core()
        pieces, start = [], 0
        for jump in np.flatnonzero(core[:, 1] - core[:, 0] > JUMP_M):
            pieces.append(core[start:jump])
            start = jump + 1
        pieces.append(core[start:])
        return [p for p in pieces if len(p) and p[-1, 3] - p[0, 2] >= MIN_CORE_MM]


def secdist_at(depths: np.ndarray, core: np.ndarray) -> np.ndarray:
    """mm along the row at each depth, through Section.core()'s steps. A depth
    a block sits at maps to the block's far side, so the block is skipped."""
    index = np.clip(np.searchsorted(core[:, 0], depths, side="right") - 1, 0, len(core) - 1)
    d0, d1, x0, x1 = core[index].T
    t = np.clip((depths - d0) / (d1 - d0), 0.0, 1.0)
    return x0 + t * (x1 - x0)


def read_header(package: Path, hole: str) -> dict:
    """The key = value / key :value lines at the top of <hole>_tsg.tsg -
    UWI, WAMEX report, lat/lon + datum, scan date. 0,0 lat/lon (the MPWD
    packages) means not recorded."""
    path = package / f"{hole}_tsg.tsg"
    if not path.is_file():
        return {}
    with path.open("rb") as handle:
        text = handle.read(64_000).decode("latin-1", errors="replace")
    header = {}
    for line in re.split(r"[\r\n]+", text):
        match = re.match(r"^([A-Za-z][\w ]*?)\s*(?:=|\s:)\s*(.*)$", line)
        if match:
            header.setdefault(match.group(1).strip().lower(), match.group(2).strip())
    summary = header.get("executive summary", "")
    if (uwi := re.search(r"UWI:\s*(\w+)", summary)):
        header["uwi"] = uwi.group(1)
    if (report := re.search(r"WAMEX Report ID:\s*(\w+)", summary)):
        header["wamex_report"] = report.group(1)
    try:
        lat, lon = map(float, header.get("lat lon", "").split()[:2])
        header["latlon"] = (lat, lon) if (lat, lon) != (0.0, 0.0) else None
    except ValueError:
        header["latlon"] = None
    return header


def read_sections(package: Path) -> tuple[dict[int, list[Section]], str]:
    """{tray: [Section, ... top-to-bottom]} from the package's scalars, plus
    which mineral-group column coloured them."""
    from pytsg import parse_tsg  # heavy import, only needed here

    with warnings.catch_warnings(), np.errstate(all="ignore"):
        warnings.simplefilter("ignore")  # pytsg's describe() overflows on TSG's -FLT_MAX nulls
        tsg = parse_tsg.read_package(str(package))

    needed = {"Tray", "Section", "SecDist (mm)", "Depth (m)"}
    region = next((r for r in (tsg.nir, tsg.tir)
                   if isinstance(getattr(r, "scalars", None), pd.DataFrame) and needed <= set(r.scalars.columns)),
                  None)
    if region is None:
        raise ValueError(f"no TSG scalars with {sorted(needed)} under {package} - can't place rows")
    scalars = region.scalars

    group_column = next((c for c in GROUP_COLUMNS if c in scalars.columns), None)
    # pytsg only decodes some rows of a classified column to their names
    # (KD1's are all still raw codes - see tsg_bridge.py), so decode through
    # the package's own class table rather than trust a mix.
    class_names = {}
    for band in region.bandheaders or []:
        if band.name == group_column and band.class_number in (region.classes or {}):
            class_names = region.classes[band.class_number].classes

    def group_of(value, valid) -> str | None:
        if not valid:
            return None
        if isinstance(value, str):
            name = value.strip()
        else:
            try:
                name = class_names.get(int(value))
            except (TypeError, ValueError):
                return None
        return resolve_group(name) if name and name.upper() not in NOT_ROCK else None

    trays: dict[int, list[Section]] = {}
    for number, rows in scalars.groupby("Section", sort=True):
        rows = rows.sort_values("SecDist (mm)")
        tray = int(pd.to_numeric(rows["Tray"], errors="coerce").iloc[0])
        valid = rows["Final Mask"].to_numpy() > 0 if "Final Mask" in rows else np.ones(len(rows), bool)
        values = rows[group_column].tolist() if group_column else [None] * len(rows)
        typed = rows.get("Interactive Depth Logging")
        markers = []
        if typed is not None:
            # A plain positive depth is one typed in at a core block; -depth is
            # a row start/end anchor, +/-2^24 flags a no-core span, -FLT_MAX is null.
            markers = [(float(x), float(v)) for x, v in zip(rows["SecDist (mm)"], typed) if 0 < v < 1e5]
        trays.setdefault(tray, []).append(Section(
            tray=tray, number=int(number),
            secdist=rows["SecDist (mm)"].to_numpy(dtype=float),
            depth=rows["Depth (m)"].to_numpy(dtype=float),
            groups=[group_of(v, ok) for v, ok in zip(values, valid)],
            markers=markers,
        ))
    return trays, group_column or ""


def read_linescan_tables(package: Path, hole: str) -> dict[int, dict] | None:
    """{tray: {"length_mm", "band_mm", "rows"}} from the linescan's own tray and
    section tables - its 64-byte header, chunk index and the tables after the
    imagery, never the (multi-GB) imagery itself. None without a linescan."""
    path = package / f"{hole}_tsg_cras.bip"
    if not path.is_file():
        return None
    from pytsg.parse_tsg import CrasHeader, SectionInfo, TrayInfo

    with path.open("rb") as handle:
        header = CrasHeader(*struct.unpack("20s2I8h4I2h", handle.read(64)))
        offsets = np.frombuffer(handle.read(4 * (header.nchunks + 1)), np.uint32).astype(np.int64)
        wrapped = np.flatnonzero(np.diff(offsets) < 0)  # >4 GB linescans wrap their uint32 offsets
        if len(wrapped):
            offsets[wrapped[0] + 1:] += 1 << 32
        handle.seek(64 + 4 * (header.nchunks + 1) + int(offsets[-1] - offsets[0]))
        tray_info = [TrayInfo(*struct.unpack("3f2i", handle.read(20))) for _ in range(header.ntrays)]
        section_info = [SectionInfo(*struct.unpack("4f3i", handle.read(28))) for _ in range(header.nsections)]
    if header.finerep:
        raise ValueError(f"{hole} is a chip-tray dataset (finerep={header.finerep}), not rows of core")

    tables, cursor = {}, 0
    for number, tray in enumerate(tray_info, start=1):
        sections = section_info[cursor:cursor + tray.nsections]
        cursor += tray.nsections
        tables[number] = {
            "length_mm": float(tray.utlengthmm),
            "band_mm": float(np.median([s.trimwidthmm for s in sections])) if sections else None,
            "rows": tray.nsections,
        }
    return tables


# --------------------------------------------------------------------------
# where things are in a tray photo
# --------------------------------------------------------------------------

@dataclass
class PlotGeometry:
    x0: float        # pixel column of SecDist 0 (the x axis' first tick)
    y0: int          # first pixel row of the tray image, under the title bar
    y1: int          # the x-axis line, just under the tray image
    px_per_mm: float
    bands: int
    ticks: int       # 50 mm ticks the scale was fitted to (0 = fell back to the frame width)
    frame_x1: int    # last column of the tray image

    def x_at(self, secdist_mm):
        return self.x0 + np.asarray(secdist_mm, dtype=float) * self.px_per_mm

    def band(self, index: int) -> tuple[float, float]:
        height = (self.y1 - self.y0) / self.bands
        return self.y0 + index * height, self.y0 + (index + 1) * height

    @property
    def band_mm(self) -> float:
        return (self.y1 - self.y0) / self.bands / self.px_per_mm


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """[(start, stop), ...] of the True runs in a 1D bool array."""
    edges = np.flatnonzero(np.diff(np.concatenate([[0], mask.astype(np.int8), [0]])))
    return list(zip(edges[::2].tolist(), edges[1::2].tolist()))


def plot_geometry(photo: np.ndarray, bands: int, length_mm: float) -> PlotGeometry:
    """Where TSG drew the tray image inside its render: the title bar and the
    axis area are black, the plot isn't (not even very dark serpentinite
    clears NON_BLACK on less than half a row, because the rails don't)."""
    lit = photo.max(axis=2) > NON_BLACK
    height, width = lit.shape
    across = lit[:, width // 10: width - width // 10].mean(axis=1)
    rows = np.flatnonzero(across >= PLOT_FILL)
    if len(rows) == 0:
        raise ValueError("no tray image inside the render")
    y0, y1 = int(rows[0]), int(rows[-1])
    down = lit[y0:y1].mean(axis=0)
    cols = np.flatnonzero(down >= PLOT_FILL)
    frame_x0, frame_x1 = int(cols[0]), int(cols[-1])

    # The x axis' ticks hang just under its line, white on black. Their
    # spacing differs between renders - 50 mm on GDD005/KD1, 10 mm on MPWD10
    # (4 px/mm, and an 830 mm tray) - so it's read off the frame's rough
    # scale (frame width / scan length), then the ticks give the exact one.
    under = photo[y1 + 1: y1 + 6, max(0, frame_x0 - 4): frame_x1 + 5]
    centres = np.array([(a + b - 1) / 2 for a, b in _runs((under.min(axis=2) > 150).any(axis=0))])
    centres = centres + max(0, frame_x0 - 4)
    frame_scale = (frame_x1 + 1 - frame_x0) / length_mm
    x0, px_per_mm, ticks = float(frame_x0), frame_scale, 0
    if len(centres) >= 5:
        spacing = np.median(np.diff(centres))
        tick_mm = min(NICE_TICKS_MM, key=lambda mm: abs(spacing / frame_scale - mm))
        mm = np.round((centres - frame_x0) / spacing) * tick_mm
        keep = np.ones(len(centres), bool)
        for _ in range(2):  # refit without anything that isn't on the tick grid
            slope, intercept = np.polyfit(mm[keep], centres[keep], 1)
            keep = np.abs(centres - (intercept + slope * mm)) <= 2.0
            if keep.sum() < 5:
                break
        if keep.sum() >= 5 and abs(slope / frame_scale - 1) < 0.05:
            x0, px_per_mm, ticks = float(intercept), float(slope), int(keep.sum())
    return PlotGeometry(x0, y0, y1, px_per_mm, bands, ticks, frame_x1)


def row_image(photo: np.ndarray, geometry: PlotGeometry, band: int, core: np.ndarray,
              width: int, height: int) -> Image.Image:
    """One row of core, depth-true: `height` pixel rows evenly spaced in depth
    from its first to last core depth, shallowest on top, `width` across.
    Rotated 90 deg clockwise, as core_strip.py does - the row's left (shallow)
    end becomes the top."""
    top, bottom = geometry.band(band)
    y_lo, y_hi = int(round(top)), int(round(bottom))
    x_lo, x_hi = float(geometry.x_at(core[0, 2])), float(geometry.x_at(core[-1, 3]))
    ix_lo = max(0, int(math.floor(x_lo)))
    ix_hi = min(photo.shape[1] - 1, int(math.ceil(x_hi)) + 1)
    crop = photo[y_lo:y_hi, ix_lo:ix_hi + 1].astype(np.float32)

    # Sample at the photo's own resolution first, then let LANCZOS do the
    # (anti-aliased) resize to the output scale.
    depth_from, depth_to = core[0, 0], core[-1, 1]
    native = max(2, int(round((depth_to - depth_from) * 1000 * geometry.px_per_mm)))
    depths = depth_from + (np.arange(native) + 0.5) * (depth_to - depth_from) / native
    columns = np.clip(geometry.x_at(secdist_at(depths, core)) - ix_lo, 0, crop.shape[1] - 1.001)
    left = np.floor(columns).astype(int)
    weight = (columns - left)[None, :, None]
    sampled = crop[:, left] * (1 - weight) + crop[:, left + 1] * weight   # (across, depth, rgb)
    upright = np.ascontiguousarray(np.rot90(sampled, k=-1))                # (depth, across, rgb)
    image = Image.fromarray(np.clip(upright + 0.5, 0, 255).astype(np.uint8))
    return image.resize((max(1, width), max(1, height)), Image.Resampling.LANCZOS)


# --------------------------------------------------------------------------
# the GSWA collar
# --------------------------------------------------------------------------

def load_catalog(path: Path) -> pd.DataFrame | None:
    if not path.is_file():
        return None
    catalog = pd.read_excel(path)
    catalog["_name"] = catalog["Well Name and Info"].astype(str).str.strip().str.upper()
    catalog["_uwi"] = catalog["Unique Well Identifier"].astype(str).str.strip().str.upper()
    return catalog


def _number(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) else number


def match_catalog(catalog: pd.DataFrame | None, hole: str, header: dict) -> tuple[pd.Series | None, str]:
    """The hole's catalog row and how it was matched ("uwi" / "name"), or
    (None, why not)."""
    if catalog is None:
        return None, "no catalog"
    if header.get("uwi"):
        hits = catalog[catalog["_uwi"] == header["uwi"].upper()]
        if len(hits) == 1:
            return hits.iloc[0], "uwi"
    names = {hole.upper(), header.get("drillhole name", "").upper(), header.get("dataset name", "").upper()} - {""}
    hits = catalog[catalog["_name"].isin(names)]
    if header.get("latlon") is not None and len(hits):
        near = [distance_km(header["latlon"], (_number(r["Latitude (degrees)"]), _number(r["Longitude (degrees)"])))
                if _number(r["Latitude (degrees)"]) is not None else None for _, r in hits.iterrows()]
        hits = hits[[km is not None and km <= SAME_HOLE_KM for km in near]]
    if len(hits) == 1:
        return hits.iloc[0], "name"
    if len(hits) > 1:
        return None, f"{len(hits)} catalog rows named {sorted(names)} and nothing to tell them apart"
    return None, "not in catalog"


def collar_block(row: pd.Series, how: str, header: dict, depths: list[float]) -> dict:
    """GDA2020 + MGA2020 collar, orientation and a straight-line trace
    through `depths` for one catalog row, with every assumption written in."""
    from pyproj import Transformer

    notes = []
    datum = str(row.get("Original Datum", "")).strip().upper()
    if datum not in DATUM_EPSG:
        notes.append(f"catalog datum {datum or 'blank'!r} not recognised - assumed GDA94")
        datum = "GDA94"
    lat, lon = _number(row.get("Latitude (degrees)")), _number(row.get("Longitude (degrees)"))
    easting, northing, zone = _number(row.get("Easting")), _number(row.get("Northing")), _number(row.get("Zone"))
    grid_offset = None
    if lat is not None and lon is not None:
        to_2020 = Transformer.from_crs(f"EPSG:{DATUM_EPSG[datum]}", "EPSG:7844", always_xy=True)
        lon20, lat20 = to_2020.transform(lon, lat)
        # The catalog's own easting/northing don't always agree with its
        # lat/lon: GDD005's easting is 136 m off, and 100 of the 1,556 GDA94
        # rows that have both differ by >50 m (52 by >1 km - wrong zone,
        # swapped values). Lat/lon is what the TSG header and NVCL carry, so
        # it wins; the disagreement is recorded, not silently dropped.
        if easting is not None and northing is not None and zone is not None and datum in GRID_EPSG_BASE:
            to_grid = Transformer.from_crs(f"EPSG:{DATUM_EPSG[datum]}", f"EPSG:{GRID_EPSG_BASE[datum] + int(zone)}",
                                           always_xy=True)
            e, n = to_grid.transform(lon, lat)
            grid_offset = math.hypot(e - easting, n - northing)
            if grid_offset > 20:
                notes.append(f"catalog easting/northing are {grid_offset:,.0f} m from its own lat/lon - lat/lon used")
    elif easting is not None and northing is not None and zone is not None and datum in GRID_EPSG_BASE:
        to_2020 = Transformer.from_crs(f"EPSG:{GRID_EPSG_BASE[datum] + int(zone)}", "EPSG:7844", always_xy=True)
        lon20, lat20 = to_2020.transform(easting, northing)
        notes.append("no lat/lon in the catalog - collar from its easting/northing")
    else:
        raise ValueError("catalog row has neither lat/lon nor easting/northing")

    mga_zone = int((lon20 + 180) // 6) + 1
    to_mga = Transformer.from_crs("EPSG:7844", f"EPSG:{7800 + mga_zone}", always_xy=True)
    from_mga = Transformer.from_crs(f"EPSG:{7800 + mga_zone}", "EPSG:7844", always_xy=True)
    e0, n0 = to_mga.transform(lon20, lat20)

    elevation = _number(row.get("Elevation"))
    if elevation == 0:
        elevation = None  # the catalog's placeholder, see holes_3d.py
    dip, azimuth = _number(row.get("Inclination (dip)")), _number(row.get("Azimuth"))
    if dip is None:
        notes.append("no dip in the catalog - trace drawn vertical")
    if azimuth is None:
        notes.append("no azimuth in the catalog - taken as 0")

    dip_r, az_r = math.radians(dip if dip is not None else -90.0), math.radians(azimuth or 0.0)
    trace = []
    for depth in depths:
        e = e0 + depth * math.cos(dip_r) * math.sin(az_r)
        n = n0 + depth * math.cos(dip_r) * math.cos(az_r)
        x, y = from_mga.transform(e, n)
        point = {"depth_m": round(depth, 3), "longitude": round(x, 7), "latitude": round(y, 7)}
        drop = depth * math.sin(dip_r)  # dip is negative down
        if elevation is not None:
            point["elevation_m"] = round(elevation + drop, 2)
        else:
            point["z_from_collar_m"] = round(drop, 2)
        trace.append(point)

    header_km = distance_km(header.get("latlon"), (lat, lon)) if lat is not None else None
    uwi = row.get("Unique Well Identifier")
    return {
        "hole_name": str(row.get("Well Name and Info")),
        "uwi": None if pd.isna(uwi) else str(uwi),
        "matched_by": how,
        "project": None if pd.isna(row.get("Project")) else str(row.get("Project")),
        "commodity": None if pd.isna(row.get("Commodity")) else str(row.get("Commodity")),
        "wamex_report": None if pd.isna(row.get("Drill Report")) else str(row.get("Drill Report")),
        "core_library": None if pd.isna(row.get("Archived at")) else str(row.get("Archived at")),
        "catalog_crs": {"datum": datum, "latitude": lat, "longitude": lon,
                        "easting": easting, "northing": northing, "zone": zone,
                        "grid_vs_latlon_m": None if grid_offset is None else round(grid_offset, 1)},
        "gda2020": {"epsg": 7844, "longitude": round(lon20, 7), "latitude": round(lat20, 7),
                    "transformation": to_2020.description},
        "mga2020": {"epsg": 7800 + mga_zone, "zone": mga_zone, "easting": round(e0, 2), "northing": round(n0, 2)},
        "elevation_m": elevation,
        "elevation_source": "catalog (m, assumed AHD)" if elevation is not None else "missing",
        "dip_deg": dip,
        "azimuth_deg": azimuth,
        "azimuth_reference": "not stated by the catalog (true, grid or magnetic)",
        "catalog_depth_from_m": _number(row.get("Depth from (m)")),
        "catalog_depth_to_m": _number(row.get("Depth to (m)")),
        "trace": {
            "method": "straight line from the collar dip/azimuth - the catalog has no downhole survey",
            "points": trace,
        },
        "tsg_header_km_from_catalog": None if header_km is None else round(header_km, 3),
        "notes": notes,
    }


# --------------------------------------------------------------------------
# output
# --------------------------------------------------------------------------

class SheetWriter:
    """Depth-aligned sheets written as rows arrive shallow-to-deep, so a
    whole hole's core is never in memory at once. `edges` are the sheets'
    pixel boundaries on one hole-wide y axis (pixel y = depth)."""

    def __init__(self, out_dir: Path, edges: list[int], width: int):
        self.out_dir, self.edges, self.width = out_dir, edges, width
        self.open: dict[int, tuple[Image.Image, Image.Image]] = {}
        self.written: set[int] = set()

    def _sheet(self, index: int) -> tuple[Image.Image, Image.Image]:
        if index not in self.open:
            size = (self.width, self.edges[index + 1] - self.edges[index])
            self.open[index] = (Image.new("RGB", size, NO_CORE_RGB), Image.new("RGB", size, NO_CORE_RGB))
        return self.open[index]

    def spans(self, y_from: int, y_to: int):
        for index in range(len(self.edges) - 1):
            a, b = max(y_from, self.edges[index]), min(y_to, self.edges[index + 1])
            if a < b:
                yield index, a, b

    def paste(self, image: Image.Image, y: int, x: int):
        for index, a, b in self.spans(y, y + image.height):
            photo, _ = self._sheet(index)
            photo.paste(image.crop((0, a - y, image.width, b - y)), (x, a - self.edges[index]))

    def paint(self, colour: tuple[int, int, int], y_from: int, y_to: int):
        for index, a, b in self.spans(y_from, y_to):
            _, mineral = self._sheet(index)
            mineral.paste(colour, (0, a - self.edges[index], self.width, b - self.edges[index]))

    def flush_before(self, y: int):
        """Write every sheet that ends at or above pixel y - nothing later can touch it."""
        for index in [i for i in self.open if self.edges[i + 1] <= y]:
            self._save(index)

    def close(self):
        for index in range(len(self.edges) - 1):
            if index not in self.written:
                self._save(index)

    def _save(self, index: int):
        photo, mineral = self._sheet(index)
        photo.save(self.out_dir / f"sheet_{index}.jpg", quality=88)
        mineral.save(self.out_dir / f"tsg_sheet_{index}.png")
        self.open.pop(index, None)
        self.written.add(index)


def _font(size: int):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default()


def overview_page(photo: Image.Image, mineral: Image.Image, top_m: float,
                  markers: list[float], legend: list[tuple[str, float]], title: str, subtitle: str) -> Image.Image:
    """The whole hole on one page: OVERVIEW_COLUMN_M-metre columns side by
    side, core photo + mineral strip, depth every 5 m, block markers ticked."""
    column_px = int(OVERVIEW_COLUMN_M * OVERVIEW_PX_PER_M)
    columns = max(1, math.ceil(photo.height / column_px))
    gutter, pitch, top = 46, 46 + OVERVIEW_PHOTO_W + 2 + OVERVIEW_MINERAL_W + 20, 96
    legend_rows = math.ceil(len(legend) / 4) if legend else 0
    page = Image.new("RGB", (max(760, 24 + columns * pitch), top + column_px + 44 + 22 * legend_rows), (250, 250, 248))
    draw = ImageDraw.Draw(page)
    draw.text((24, 14), title, fill=(20, 20, 20), font=_font(20))
    for i, line in enumerate(subtitle.split("\n")):
        draw.text((24, 44 + 18 * i), line, fill=(90, 90, 90), font=_font(13))
    small = _font(11)
    for column in range(columns):
        x = 24 + column * pitch + gutter
        a, b = column * column_px, min(photo.height, (column + 1) * column_px)
        page.paste(photo.crop((0, a, photo.width, b)), (x, top))
        page.paste(mineral.crop((0, a, mineral.width, b)), (x + OVERVIEW_PHOTO_W + 2, top))
        draw.rectangle((x - 1, top - 1, x + OVERVIEW_PHOTO_W + 2 + OVERVIEW_MINERAL_W, top + b - a), outline=(160, 160, 160))
        first = top_m + column * OVERVIEW_COLUMN_M
        for tick in range(0, int(OVERVIEW_COLUMN_M) + 1, 5):
            y = top + tick * OVERVIEW_PX_PER_M
            if y > top + b - a:
                break
            draw.line((x - 6, y, x - 1, y), fill=(60, 60, 60))
            label = f"{first + tick:g}"
            draw.text((x - 9 - draw.textlength(label, font=small), y - 7), label, fill=(60, 60, 60), font=small)
        for depth in markers:
            y = top + (depth - top_m) * OVERVIEW_PX_PER_M - a
            if 0 <= y - top <= b - a:
                draw.line((x - 4, y, x + 3, y), fill=(214, 140, 20), width=2)
    y = top + column_px + 18
    for i, (group, metres) in enumerate(legend):
        x = 24 + (i % 4) * 185
        yy = y + (i // 4) * 22
        draw.rectangle((x, yy, x + 14, yy + 14), fill=hex_to_rgb(MINERAL_COLOURS.get(group, UNKNOWN_COLOUR)))
        draw.text((x + 20, yy), f"{group}  {metres:.0f} m", fill=(40, 40, 40), font=small)
    return page


def build_pole(hole: str, packages: Path = PACKAGES_DIR, catalog: pd.DataFrame | None = None,
               out_root: Path = OUTPUT_DIR, px_per_mm: float = PX_PER_MM, sheet_m: float = SHEET_M,
               qa_images: bool = False) -> Path:
    package = packages / hole
    photos = sorted((int(m["tray"]), p) for p in package.glob("*.jp*g")
                    if (m := TRAY_PHOTO.match(p.name)) and m["hole"].upper() == hole.upper())
    if not photos:
        raise FileNotFoundError(f"no {hole}_NNNN.jpg tray photos in {package}")
    header = read_header(package, hole)
    sections, group_column = read_sections(package)
    linescan = read_linescan_tables(package, hole)
    warnings_: list[str] = []
    # The linescan numbers its trays by position, the scalars by tray label,
    # and they drift apart when a tray was dropped from the spectral data
    # (MPWD3: the linescan keeps a tray 2 the scalars don't have). A table
    # that doesn't line up would only raise false alarms, so it isn't used.
    if linescan:
        misfits = [t for t, s in sections.items() if linescan.get(t, {}).get("rows") != len(s)]
        if len(linescan) != len(sections) or misfits:
            warnings_.append(f"linescan tray table ({len(linescan)} trays) doesn't line up with the scan data's "
                             f"({len(sections)} trays, {len(misfits)} with other row counts) - band widths not cross-checked")
            linescan = None

    # Pass 1: every row's depths and pixel box - no image work yet.
    rows, empty_rows, tray_checks = [], [], []
    photographed = {tray for tray, _ in photos}
    for tray, path in photos:
        tray_sections = sections.get(tray)
        if not tray_sections:
            warnings_.append(f"{path.name}: no TSG scan data for tray {tray} - photo not used")
            continue
        with Image.open(path) as image:
            photo = np.asarray(image.convert("RGB"))
        spacing = float(np.median(np.diff(tray_sections[0].secdist)))
        length_mm = (linescan or {}).get(tray, {}).get("length_mm") or len(tray_sections[0].secdist) * spacing
        geometry = plot_geometry(photo, len(tray_sections), length_mm)
        check = {"tray": tray, "photo": path.name, "rows": len(tray_sections),
                 "px_per_mm": round(geometry.px_per_mm, 4), "ticks": geometry.ticks,
                 "band_mm": round(geometry.band_mm, 2),
                 "plot_px": [round(geometry.x0, 1), geometry.y0, geometry.frame_x1, geometry.y1]}
        # Without a linescan, the frame is the only check on the scale. TSG
        # draws it a little past the scan's end on some datasets (KD1 +7 px,
        # MPWD11 +66 px on every tray), so only a bigger miss counts.
        expected_x1 = geometry.x0 + length_mm * geometry.px_per_mm
        if not linescan and abs(expected_x1 - geometry.frame_x1) > 0.025 * (geometry.frame_x1 - geometry.x0):
            warnings_.append(f"{path.name}: the axis puts the end of the scan at x={expected_x1:.0f}, "
                             f"the frame at {geometry.frame_x1} - check the px/mm (qa image)")
        if linescan and tray in linescan:
            check["linescan_band_mm"] = round(linescan[tray]["band_mm"], 2)
            if linescan[tray]["rows"] != len(tray_sections):
                warnings_.append(f"{path.name}: linescan has {linescan[tray]['rows']} rows, scalars {len(tray_sections)}")
            if abs(geometry.band_mm / linescan[tray]["band_mm"] - 1) > BAND_TOLERANCE:
                warnings_.append(f"{path.name}: photo rows are {geometry.band_mm:.1f} mm apart but the linescan's "
                                 f"sections {linescan[tray]['band_mm']:.1f} mm wide - check the cut (qa image)")
        tray_checks.append(check)

        for band, section in enumerate(tray_sections):
            pieces = section.core_pieces()
            if not pieces:
                empty_rows.append({"tray": tray, "row_in_tray": band + 1, "section": section.number,
                                   "depth_m": round(float(section.depth.max()), 3)})
                continue
            top, bottom = geometry.band(band)
            for piece, core in enumerate(pieces, start=1):
                rows.append({
                    "tray": tray, "row_in_tray": band + 1, "section": section.number, "piece": piece,
                    "source_file": path.name, "band": band, "geometry": geometry, "core": core,
                    "depth_from": float(core[0, 0]), "depth_to": float(core[-1, 1]),
                    "band_px": (int(round(top)), int(round(bottom))),
                    "core_mm": float(core[-1, 3] - core[0, 2]),
                    "section_obj": section,
                })
    for tray in sorted(set(sections) - photographed):
        warnings_.append(f"tray {tray} has TSG scan data but no {hole}_{tray:04d}.jpg")
    if not rows:
        raise ValueError(f"{hole}: no rows of core found")

    rows.sort(key=lambda r: (r["depth_from"], r["tray"], r["row_in_tray"]))
    depth_min, depth_max = rows[0]["depth_from"], max(r["depth_to"] for r in rows)
    px_per_m = px_per_mm * 1000.0

    def y_of(depth: float) -> int:
        return int(round((depth - depth_min) * px_per_m))

    gaps, overlaps, reached, previous = [], [], depth_min, None
    for row in rows:
        if row["depth_from"] - reached > GAP_REPORT_M:
            where = (f"inside tray {row['tray']} row {row['row_in_tray']} - TSG logs no core there"
                     if previous["section"] == row["section"] else
                     f"between tray {previous['tray']} row {previous['row_in_tray']} "
                     f"and tray {row['tray']} row {row['row_in_tray']}")
            gaps.append({"depth_from_m": round(reached, 3), "depth_to_m": round(row["depth_from"], 3),
                         "length_m": round(row["depth_from"] - reached, 3), "where": where})
        elif reached - row["depth_from"] > GAP_REPORT_M:
            overlaps.append({"tray": row["tray"], "row_in_tray": row["row_in_tray"],
                             "overlap_m": round(reached - row["depth_from"], 3)})
        reached, previous = max(reached, row["depth_to"]), row
    if overlaps:
        warnings_.append(f"{len(overlaps)} row(s) start above where the previous one ended - "
                         "TSG depths overlap there, later rows are drawn over earlier ones")

    widths = {id(r): max(1, int(round((r["band_px"][1] - r["band_px"][0]) / r["geometry"].px_per_mm * px_per_mm)))
              for r in rows}
    sheet_width = max(widths.values())
    boundaries = [depth_min] + [k * sheet_m for k in range(math.floor(depth_min / sheet_m) + 1,
                                                          math.ceil(depth_max / sheet_m))] + [depth_max]
    edges = [y_of(d) for d in boundaries]

    out_dir = out_root / hole
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in [*out_dir.glob("sheet_*.jpg"), *out_dir.glob("tsg_sheet_*.png")]:
        if int(re.sub(r"\D", "", stale.stem) or 0) >= len(edges) - 1:
            stale.unlink()  # left by an earlier run that made more sheets
    writer = SheetWriter(out_dir, edges, sheet_width)

    overview_top = math.floor(depth_min / OVERVIEW_COLUMN_M) * OVERVIEW_COLUMN_M
    overview_bottom = math.ceil(depth_max / OVERVIEW_COLUMN_M) * OVERVIEW_COLUMN_M
    overview_h = int(round((overview_bottom - overview_top) * OVERVIEW_PX_PER_M))
    overview_photo = Image.new("RGB", (OVERVIEW_PHOTO_W, overview_h), NO_CORE_RGB)
    overview_mineral = Image.new("RGB", (OVERVIEW_MINERAL_W, overview_h), NO_CORE_RGB)

    def overview_y(depth: float) -> int:
        return int(round((depth - overview_top) * OVERVIEW_PX_PER_M))

    # Pass 2: cut, resample and place every row, shallow to deep.
    table_rows, markers, metres_by_group = [], [], {}
    loaded = (None, None)
    qa_draw: dict[int, tuple[Image.Image, ImageDraw.ImageDraw]] = {}
    for row in rows:
        if loaded[0] != row["source_file"]:
            with Image.open(package / row["source_file"]) as image:
                loaded = (row["source_file"], np.asarray(image.convert("RGB")))
        photo, geometry, core, section = loaded[1], row["geometry"], row["core"], row["section_obj"]
        y_from, y_to = y_of(row["depth_from"]), y_of(row["depth_to"])
        if y_to <= y_from:
            continue
        writer.flush_before(y_from)
        width = widths[id(row)]
        image = row_image(photo, geometry, row["band"], core, width, y_to - y_from)
        x_off = (sheet_width - width) // 2
        writer.paste(image, y_from, x_off)
        oy_from, oy_to = overview_y(row["depth_from"]), overview_y(row["depth_to"])
        if oy_to > oy_from:
            overview_photo.paste(image.resize((OVERVIEW_PHOTO_W, oy_to - oy_from), Image.Resampling.BOX), (0, oy_from))

        # Every scan sample's group, over the depth half-way to its neighbours.
        mids = np.concatenate([[section.depth[0]], (section.depth[1:] + section.depth[:-1]) / 2, [section.depth[-1]]])
        row_groups: dict[str, float] = {}
        for i, group in enumerate(section.groups):
            lo, hi = max(mids[i], row["depth_from"]), min(mids[i + 1], row["depth_to"])
            if hi <= lo:
                continue
            colour = hex_to_rgb(MINERAL_COLOURS.get(group, UNKNOWN_COLOUR) if group else UNKNOWN_COLOUR)
            writer.paint(colour, y_of(lo), y_of(hi))
            if overview_y(hi) > overview_y(lo):
                overview_mineral.paste(colour, (0, overview_y(lo), OVERVIEW_MINERAL_W, overview_y(hi)))
            if group:
                row_groups[group] = row_groups.get(group, 0.0) + (hi - lo)
                metres_by_group[group] = metres_by_group.get(group, 0.0) + (hi - lo)
        if row["piece"] == 1:
            markers.extend({"depth_m": round(depth, 3), "tray": row["tray"], "row_in_tray": row["row_in_tray"],
                            "secdist_mm": round(secdist, 1)} for secdist, depth in section.markers)

        # One table row per sheet the row lands on, in core_strip.py's shape
        # (crop_box = the matching stretch of the source photo, pre-rotation).
        span = row["depth_to"] - row["depth_from"]
        for index, a, b in writer.spans(y_from, y_to):
            d_a, d_b = depth_min + a / px_per_m, depth_min + b / px_per_m
            x_a, x_b = geometry.x_at(secdist_at(np.array([d_a, d_b]), core))
            table_rows.append({
                "sheet_index": index,
                "y_from_px": a - edges[index], "y_to_px": b - edges[index],
                "x_from_px": x_off, "x_to_px": x_off + width,
                "depth_from_m": round(d_a, 4), "depth_to_m": round(d_b, 4),
                "tray": row["tray"], "row_in_tray": row["row_in_tray"], "piece": row["piece"],
                "tsg_section": row["section"], "source_file": row["source_file"],
                "crop_box": [round(float(x_a), 1), row["band_px"][0], round(float(x_b), 1), row["band_px"][1]],
                "core_width_mm": round(width / px_per_mm, 1),
                "depth_per_core_m": round(span / (row["core_mm"] / 1000), 3),
                "mineral_group": max(row_groups, key=row_groups.get) if row_groups else None,
            })

        if qa_images:
            if row["tray"] not in qa_draw:
                with Image.open(package / row["source_file"]) as image:
                    shown = image.convert("RGB")
                qa_draw[row["tray"]] = (shown, ImageDraw.Draw(shown))
            shown, draw = qa_draw[row["tray"]]
            x_a, x_b = float(geometry.x_at(core[0, 2])), float(geometry.x_at(core[-1, 3]))
            draw.rectangle((x_a, row["band_px"][0] + 3, x_b, row["band_px"][1] - 3), outline=(0, 255, 60), width=4)
            draw.text((x_a + 8, row["band_px"][0] + 8), f"{row['depth_from']:.2f}-{row['depth_to']:.2f} m",
                      fill=(0, 255, 60), font=_font(30), stroke_width=2, stroke_fill=(0, 0, 0))
            for secdist, depth in section.markers:
                x = float(geometry.x_at(secdist))
                draw.line((x, row["band_px"][0], x, row["band_px"][1]), fill=(255, 170, 0), width=4)
                draw.text((x + 6, row["band_px"][1] - 42), f"{depth:g}", fill=(255, 170, 0), font=_font(28),
                          stroke_width=2, stroke_fill=(0, 0, 0))
    writer.close()

    if qa_images:
        (out_dir / "qa").mkdir(exist_ok=True)
        for empty in empty_rows:
            if empty["tray"] in qa_draw:
                shown, draw = qa_draw[empty["tray"]]
                check = next(c for c in tray_checks if c["tray"] == empty["tray"])
                band_h = (check["plot_px"][3] - check["plot_px"][1]) / check["rows"]
                y = check["plot_px"][1] + (empty["row_in_tray"] - 0.5) * band_h
                draw.text((check["plot_px"][0] + 40, y), "no core in TSG - not used", fill=(255, 60, 60),
                          font=_font(34), stroke_width=2, stroke_fill=(0, 0, 0))
        for tray, (shown, _) in qa_draw.items():
            shown.resize((shown.width // 2, shown.height // 2)).save(out_dir / "qa" / f"tray_{tray:04d}.jpg", quality=80)

    # The collar, from the GSWA catalog.
    catalog_row, how = match_catalog(catalog, hole, header)
    collar = None
    if catalog_row is not None:
        try:
            collar = collar_block(catalog_row, how, header, [0.0, depth_min, depth_max])
        except Exception as exc:  # noqa: BLE001 - a bad collar must not lose the pole
            warnings_.append(f"collar: {exc}")
    else:
        warnings_.append(f"collar: {how} - pole not placed on the map")
    if collar:
        warnings_.extend(f"collar: {note}" for note in collar["notes"])
        if collar["elevation_m"] is None:
            warnings_.append("collar: no elevation in the catalog - 3D views must take RL from a DEM or leave it relative")
        km = collar["tsg_header_km_from_catalog"]
        if km is not None and km > SAME_HOLE_KM:
            warnings_.append(f"collar: TSG header lat/lon is {km:.2f} km from the catalog's")
        for name, catalog_depth, pole_depth in (("from", collar["catalog_depth_from_m"], depth_min),
                                                ("to", collar["catalog_depth_to_m"], depth_max)):
            if catalog_depth is not None and abs(catalog_depth - pole_depth) > 0.5:
                warnings_.append(f"catalog depth {name} {catalog_depth} m vs imaged core {pole_depth:.2f} m")

    legend = sorted(metres_by_group.items(), key=lambda item: -item[1])
    where = (f"{collar['gda2020']['latitude']:.5f}, {collar['gda2020']['longitude']:.5f} GDA2020 · "
             f"dip {collar['dip_deg'] if collar['dip_deg'] is not None else 'n/a'} "
             f"az {collar['azimuth_deg'] if collar['azimuth_deg'] is not None else 'n/a'}"
             if collar else "collar not matched")
    overview_page(
        overview_photo, overview_mineral, overview_top, [m["depth_m"] for m in markers], legend,
        title=f"{hole}  ·  core {depth_min:.1f}-{depth_max:.1f} m  ·  {len(rows)} rows from {len(tray_checks)} trays",
        subtitle=f"{where}  ·  depth = HyLogger downhole depth (m)\n"
                 f"photo | TSA group ({group_column})  ·  1 m = {OVERVIEW_PX_PER_M} px down, width not to scale  ·  "
                 f"orange ticks = core-block depths  ·  dark = no core imaged",
    ).save(out_dir / "overview.jpg", quality=90)

    sheets = [{
        "sheet_index": i, "file": f"sheet_{i}.jpg", "width_px": sheet_width, "height_px": edges[i + 1] - edges[i],
        "depth_from_m": round(boundaries[i], 4), "depth_to_m": round(boundaries[i + 1], 4),
    } for i in range(len(edges) - 1)]
    imaged = sum(r["depth_to"] - r["depth_from"] for r in rows)
    table_path = out_dir / "depth_pixel_table.json"
    atomic_write_json(table_path, {
        "hole_id": hole,
        "method": "tsg-package",
        "generated_at": utc_now(),
        # views.py matches these against the holes table before serving
        # the strip on a hole (see photos_from_elsewhere).
        "source_datasets": [{
            "dataset_id": header.get("uuid"),
            "dataset_name": header.get("dataset name") or hole,
            "tsg_collar": list(header["latlon"]) if header.get("latlon") else None,
        }],
        "depth_reference": "downhole depth (m) along the hole from the collar, as logged by the HyLogger "
                           "(TSG 'Depth (m)', TIDL-corrected to core blocks)",
        "px_per_mm": px_per_mm,
        "px_per_m": px_per_m,
        "core_width_px": sheet_width,
        "depth_min_m": round(depth_min, 4),
        "depth_max_m": round(depth_max, 4),
        "sheets": sheets,
        "rows": table_rows,
        "gaps": gaps,
        "markers": markers,
        "collar": collar,
        "mineral_log": group_column,
        "qa": {
            "trays_photographed": len(photos),
            "trays_used": len(tray_checks),
            "rows_with_core": len(rows),
            "rows_without_core": empty_rows,
            "imaged_m": round(imaged, 3),
            "gap_m": round(sum(g["length_m"] for g in gaps), 3),
            "coverage_pct": round(100 * imaged / (depth_max - depth_min), 2),
            # Rows the HyLogger spread core loss through: drawn stretched, per its depths.
            "stretched_rows": [
                {"tray": r["tray"], "row_in_tray": r["row_in_tray"], "piece": r["piece"],
                 "depth_per_core_m": round((r["depth_to"] - r["depth_from"]) / (r["core_mm"] / 1000), 2)}
                for r in rows if (r["depth_to"] - r["depth_from"]) / (r["core_mm"] / 1000) > LOW_RECOVERY
            ],
            "overlaps": overlaps,
            "trays": tray_checks,
            "warnings": warnings_,
        },
        "provenance": {
            "package": package.name,
            "tsg_header": {k: header.get(k) for k in ("uwi", "wamex_report", "lat lon", "geo datum", "collar",
                                                      "drillhole name", "scan date", "hylogger name", "current owner")},
            "files": [{"file": p.name, "sha256": sha256_file(p)} for _, p in photos]
                     + [{"file": p.name, "sha256": sha256_file(p)} for p in sorted(package.glob(f"{hole}_tsg*.tsg"))],
        },
    })
    print(f"{hole}: {len(tray_checks)} trays, {len(rows)} rows, {depth_min:.2f}-{depth_max:.2f} m "
          f"({imaged:.1f} m imaged, {len(gaps)} gaps) -> {len(sheets)} sheets in {out_dir}"
          + (f"  [{len(warnings_)} warning(s)]" if warnings_ else ""))
    return table_path


def write_index(out_root: Path = OUTPUT_DIR) -> Path:
    """poles.geojson: one Point per placed pole at its GDA2020 collar - the
    layer a map loads to show which holes have core to look at."""
    features = []
    for table_path in sorted(out_root.glob("*/depth_pixel_table.json")):
        table = read_json(table_path)
        collar = table.get("collar")
        if not collar:
            continue
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [collar["gda2020"]["longitude"], collar["gda2020"]["latitude"]]},
            "properties": {
                "hole_id": table["hole_id"], "uwi": collar["uwi"], "project": collar["project"],
                "commodity": collar["commodity"], "depth_from_m": table["depth_min_m"], "depth_to_m": table["depth_max_m"],
                "coverage_pct": table["qa"]["coverage_pct"], "dip_deg": collar["dip_deg"], "azimuth_deg": collar["azimuth_deg"],
                "elevation_m": collar["elevation_m"], "sheets": len(table["sheets"]),
                "strip": f"core_strips/{table['hole_id']}/depth_pixel_table.json",
                "trace": collar["trace"]["points"], "warnings": len(table["qa"]["warnings"]),
            },
        })
    path = out_root / "poles.geojson"
    atomic_write_json(path, {"type": "FeatureCollection",
                             "crs_note": "GDA2020 lon/lat (EPSG:7844), within ~1 m of WGS84 for web maps",
                             "features": features})
    print(f"{len(features)} placed pole(s) -> {path}")
    return path


def packages_with_photos(packages: Path) -> list[str]:
    return sorted(p.name for p in packages.iterdir()
                  if p.is_dir() and (p / f"{p.name}_tsg.tsg").is_file() and any(p.glob(f"{p.name}_[0-9][0-9][0-9][0-9].jpg")))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--hole", action="append", help="package folder under --packages, e.g. GDD005 (repeatable)")
    parser.add_argument("--all", action="store_true", help="every package under --packages with tray photos")
    parser.add_argument("--packages", type=Path, default=PACKAGES_DIR)
    parser.add_argument("--catalog", type=Path, default=CATALOG_PATH, help="GSWA HyLogger catalog (collars.xlsx)")
    parser.add_argument("--out", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--px-per-mm", type=float, default=PX_PER_MM)
    parser.add_argument("--sheet-m", type=float, default=SHEET_M)
    parser.add_argument("--qa-images", action="store_true", help="also write qa/tray_NNNN.jpg with the cuts drawn on")
    args = parser.parse_args()
    if not args.hole and not args.all:
        parser.error("pass --hole <id> (repeatable) or --all")

    catalog = load_catalog(args.catalog)
    if catalog is None:
        print(f"no catalog at {args.catalog} - poles are built but not placed")
    for hole in (packages_with_photos(args.packages) if args.all else args.hole):
        try:
            build_pole(hole, args.packages, catalog, args.out, args.px_per_mm, args.sheet_m, args.qa_images)
        except Exception as exc:  # noqa: BLE001 - one bad package must not stop a batch
            print(f"{hole}: skipped - {exc}")
    write_index(args.out)
