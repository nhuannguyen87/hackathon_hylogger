#!/usr/bin/env python
"""Depth (m) <-> pixel lookups against the sheets core_strip.py builds.

The original version of this file (see the draft this replaces) was a
single global linear map: one (start_depth, end_depth) -> one
strip_pixel_width fraction for the whole hole. That's only correct if
every row was rescaled to exactly the same pixels-per-metre, which
core_strip.py does NOT guarantee (each row is independently detected and
resized) - so this reads the real per-row breakpoint table core_strip.py
writes instead of assuming linearity across the whole hole. Depth is still
treated as linear *within* a row (along that row's photographed length),
which is a real approximation, not measured per-pixel - it's the same
approximation core_strip.py documents when it allocates a tray's depth
across its rows by pixel length.

core_strip.py now stacks rows into a single narrow column per sheet
(rotated so depth runs top-to-bottom) rather than pasting each row as its
own wide band, and splits a hole across multiple sheet_N files once one
sheet would get too tall to view. So a pixel position here is
(sheet_index, x_px, y_px), not just (x_px, y_px) - two different sheets
both have rows starting at y_px=0.

Usage:
    python depth_lookup.py --hole BH01_Behemoth --depth 165.0
"""

from __future__ import annotations

import argparse
import bisect
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import read_json  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = PROJECT_ROOT / "data" / "media" / "core_strips"


@dataclass
class StripPosition:
    sheet_index: int
    sheet_file: str
    x_px: int             # constant: the ribbon's horizontal centre (core_width_px // 2)
    y_px: int              # sheet-local vertical position - resets to 0 on each new sheet
    row_index: int
    source_file: str
    x_raw: float            # pixel coords back in the ORIGINAL tray photo (pre-crop/rotate)
    y_raw: float


class DepthLookupEngine:
    """Piecewise depth <-> pixel mapping built from core_strip.py's
    per-row breakpoint table (data/media/core_strips/<hole>/depth_pixel_table.json)."""

    def __init__(self, table: dict):
        self.hole_id = table["hole_id"]
        self.core_width_px = table["core_width_px"]
        self.sheets = {s["sheet_index"]: s for s in table["sheets"]}
        self.rows = table["rows"]  # sorted by depth_from_m, contiguous, spans all sheets
        self._row_starts = [row["depth_from_m"] for row in self.rows]
        self._cum_length = [0]
        for row in self.rows:
            self._cum_length.append(self._cum_length[-1] + (row["y_to_px"] - row["y_from_px"]))
        self.total_length_px = self._cum_length[-1]
        self.depth_min_m = table["depth_min_m"]
        self.depth_max_m = table["depth_max_m"]

    @classmethod
    def from_table(cls, hole_id: str) -> "DepthLookupEngine":
        path = OUTPUT_DIR / hole_id / "depth_pixel_table.json"
        if not path.is_file():
            raise FileNotFoundError(f"{path} missing - run core_strip.py --hole {hole_id} first")
        return cls(read_json(path))

    def _row_at_depth(self, depth_m: float) -> tuple[int, dict]:
        if depth_m < self.depth_min_m or depth_m > self.depth_max_m:
            raise ValueError(
                f"{depth_m} m is outside {self.hole_id}'s imaged range "
                f"({self.depth_min_m}-{self.depth_max_m} m)"
            )
        index = bisect.bisect_right(self._row_starts, depth_m) - 1
        index = max(0, min(index, len(self.rows) - 1))
        return index, self.rows[index]

    def depth_to_pixel(self, depth_m: float) -> StripPosition:
        index, row = self._row_at_depth(depth_m)
        span = row["depth_to_m"] - row["depth_from_m"]
        fraction = (depth_m - row["depth_from_m"]) / span if span > 0 else 0.0
        fraction = min(max(fraction, 0.0), 1.0)

        y_px = int(row["y_from_px"] + fraction * (row["y_to_px"] - row["y_from_px"]))

        # crop_box is captured BEFORE the 90deg rotation, so it's still in
        # the source photo's own (horizontal-core) coordinate space.
        x0, y0, x1, y1 = row["crop_box"]
        x_raw = x0 + fraction * (x1 - x0)
        y_raw = (y0 + y1) / 2

        return StripPosition(
            sheet_index=row["sheet_index"],
            sheet_file=self.sheets[row["sheet_index"]]["file"],
            x_px=self.core_width_px // 2, y_px=y_px, row_index=index,
            source_file=row["source_file"], x_raw=x_raw, y_raw=y_raw,
        )

    def pixel_to_depth(self, sheet_index: int, y_px: int) -> float:
        candidates = [r for r in self.rows if r["sheet_index"] == sheet_index]
        if not candidates:
            raise ValueError(f"no rows on sheet {sheet_index}")
        row = next(
            (r for r in candidates if r["y_from_px"] <= y_px < r["y_to_px"]),
            candidates[-1] if y_px >= candidates[-1]["y_to_px"] else candidates[0],
        )
        row_height = row["y_to_px"] - row["y_from_px"]
        fraction = min(max((y_px - row["y_from_px"]) / row_height, 0.0), 1.0) if row_height else 0.0
        return round(row["depth_from_m"] + fraction * (row["depth_to_m"] - row["depth_from_m"]), 3)

    def depth_to_strip_fraction(self, depth_m: float) -> float:
        """Position along the WHOLE hole as one continuous 0..1 axis
        (unrolling every row across every sheet in depth order), for
        wrapping onto a cylinder's V texture coordinate - as opposed to
        depth_to_pixel's per-sheet (x, y) position in a flat image."""
        index, row = self._row_at_depth(depth_m)
        span = row["depth_to_m"] - row["depth_from_m"]
        fraction = (depth_m - row["depth_from_m"]) / span if span > 0 else 0.0
        row_length = row["y_to_px"] - row["y_from_px"]
        pixel_1d = self._cum_length[index] + fraction * row_length
        return pixel_1d / self.total_length_px if self.total_length_px else 0.0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hole", required=True)
    parser.add_argument("--depth", type=float, required=True)
    args = parser.parse_args()

    engine = DepthLookupEngine.from_table(args.hole)
    pos = engine.depth_to_pixel(args.depth)
    print(f"{args.depth} m -> sheet {pos.sheet_index} ({pos.sheet_file}) @ ({pos.x_px}, {pos.y_px}) px, row {pos.row_index}")
    print(f"           -> raw photo {pos.source_file} @ ({pos.x_raw:.0f}, {pos.y_raw:.0f}) px")
    print(f"           -> hole-wide strip fraction {engine.depth_to_strip_fraction(args.depth):.4f}")
    print(f"round-trip -> {engine.pixel_to_depth(pos.sheet_index, pos.y_px)} m")
