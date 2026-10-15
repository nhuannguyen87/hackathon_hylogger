#!/usr/bin/env python
"""What every logged metre holds beyond its one dominant mineral ->
data/metres.json, which backend load_data puts on each Measurement (mix,
mineral_1_species) for the strip-log and 3D-core hovers.

extract.py collapses each metre to one dominant SWIR mineral group plus a
confidence that mixes reading quality with how mixed the rock is. This keeps
the rest, from the same per-sample tables (data/csv/measurements/*.csv):

  swir   share (%) of each SWIR mineral group in the metre, weighted by TSA's
         Wt1-3, so a 60/40 chlorite-white mica mix stays 60/40
  tir    the same from the joint SWIR + thermal-infrared classifier (jCLST),
         which also sees silica, feldspar and pyroxene - minerals SWIR can't
  species the specific mineral behind the dominant SWIR group (TSA's Min1,
         e.g. Chlorite-Fe vs Chlorite-Mg): the commonest Min1 among readings
         of the metre's commonest Grp1 - extract.py's own rule for the group
  q      reading quality alone: how many of extract.py's coverage, spectral
         fit and signal checks failed (0-3) - not its two rock-mixing checks
  front  where kaolin-rich weathered rock gives way to fresh-rock minerals:
         {"m": metres down the hole, "gap": metres between the last weathered
         and the first fresh metre}, or null when the log doesn't capture it

Rows run one per metre from "from"; a metre with no readings is null.

Run:    python data/build_derived.py            (~1.5 min over the 9 GB of tables)
Check:  python data/build_derived.py --check
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "files"))
# same column rules and quality thresholds as the mineral log itself
from extract import BLANK, CHECKS, level2_holes, normalise, numeric, resolve_column  # noqa: E402

TABLES = ROOT / "data" / "csv" / "measurements"
LOGGED = ROOT / "data" / "measurements.csv"
OUT = ROOT / "data" / "metres.json"

CHANNELS = {"swir": ["stsas", "utsas"], "tir": ["sjclst", "ujclst"]}
QUALITY_CHECKS = [check for check in CHECKS if check[0] in ("coverage", "fit", "signal")]
# Fresh-rock minerals that don't survive weathering. White mica is left out on
# purpose: it lasts well into the kaolin-rich weathered zone.
FRESH = ["CHLORITE", "CARBONATE", "AMPHIBOLE", "DARK-MICA", "EPIDOTE", "SERPENTINE", "OTHER-MGOH"]
FRESH_RUN = 5  # metres of fresh rock in a row that mark the front
MAX_GAP_M = 30  # a longer weathered -> fresh transition is too vague to call a front


def channels(user_first: bool) -> dict[str, list[str]]:
    """CHANNELS, User results first for a hole GSWA released at Level 2 (extract.py's rule)."""
    return {kind: sorted(suffixes, key=lambda s: not s.startswith("u")) if user_first else suffixes
            for kind, suffixes in CHANNELS.items()}


def fractions(frame: pd.DataFrame, metre: pd.Series, columns: list[str], suffixes: list[str]):
    """Share of each mineral group per metre, weighted by TSA's Wt1-3."""
    suffix = next((s for s in suffixes if resolve_column(columns, [f"grp1{s}"])), None)
    if suffix is None:
        return None
    parts = []
    for k in (1, 2, 3):
        group = resolve_column(columns, [f"grp{k}{suffix}"])
        if not group:
            continue
        weight = numeric(frame, resolve_column(columns, [f"wt{k}{suffix}"]))
        if k == 1:
            weight = weight.fillna(1.0)  # a call with no weight still counts once
        parts.append(pd.DataFrame({
            "metre": metre,
            "group": frame[group].astype(str).str.strip().str.upper(),
            "w": weight,
        }))
    calls = pd.concat(parts)
    calls = calls[~calls["group"].isin(BLANK) & (calls["w"] > 0) & calls["metre"].notna()]
    if calls.empty:
        return None
    table = calls.pivot_table(index="metre", columns="group", values="w", aggfunc="sum", fill_value=0.0)
    return table.div(table.sum(axis=1), axis=0)


def species(frame: pd.DataFrame, metre: pd.Series, columns: list[str], swir=CHANNELS["swir"]) -> pd.Series | None:
    """The specific mineral behind each metre's dominant SWIR group."""
    suffix = next((s for s in swir if resolve_column(columns, [f"grp1{s}"])
                   and resolve_column(columns, [f"min1{s}"])), None)
    if suffix is None:
        return None
    calls = pd.DataFrame({
        "metre": metre,
        "group": frame[resolve_column(columns, [f"grp1{suffix}"])].astype(str).str.strip().str.upper(),
        "name": frame[resolve_column(columns, [f"min1{suffix}"])].astype(str).str.strip(),
    })
    calls = calls[~calls["group"].isin(BLANK) & calls["metre"].notna()]
    if calls.empty:
        return None
    commonest = lambda s: s.value_counts().index[0]  # noqa: E731
    top_group = calls.groupby("metre")["group"].agg(commonest)
    calls = calls[calls["group"] == calls["metre"].map(top_group)]
    return calls.groupby("metre")["name"].agg(commonest)


def quality(frame: pd.DataFrame, metre: pd.Series, columns: list[str]) -> pd.Series:
    """How many reading-quality checks each metre fails (extract.py's rules)."""
    group = resolve_column(columns, ["grp1stsas", "grp1utsas"])
    valid = ~frame[group].astype(str).str.strip().str.upper().isin(BLANK)
    found = {
        "error": resolve_column(columns, ["errorstsas", "errorutsas", "error"]),
        "snr": resolve_column(columns, ["snrstsas", "snrutsas", "snr"]),
    }
    stats = pd.DataFrame({
        "metre": metre,
        "valid": valid,
        "err": numeric(frame, found["error"]).where(valid),
        "snr": numeric(frame, found["snr"]).where(valid),
    }).groupby("metre").agg(coverage=("valid", "mean"), err=("err", "median"), snr=("snr", "median"))
    # a check we could not run is a strike, as in extract.py; a check whose
    # input this provider never logs is skipped, also as in extract.py
    active = [rule for _, needs, rule, _ in QUALITY_CHECKS if needs is None or found.get(needs)]
    return sum(rule(stats).fillna(True).astype(int) for rule in active)


def weathering_front(swir):
    """Top of the first fresh-rock run under a log that starts in kaolin-rich
    weathered rock, or None.

    ponytail: one front per hole on simple thresholds - kaolin from deeper
    hydrothermal alteration is never mistaken for it only because the log must
    start weathered; a geologist's pick wins where they differ.
    """
    if swir is None or "KAOLIN" not in swir:
        return None
    kaolin = swir["KAOLIN"].to_numpy()
    fresh = swir.reindex(columns=FRESH, fill_value=0.0).sum(axis=1).to_numpy()
    metres = swir.index.to_numpy()
    if (kaolin[:10] >= 0.5).sum() < 5:  # the log doesn't start in weathered rock
        return None
    for i in range(len(metres) - FRESH_RUN + 1):
        run = slice(i, i + FRESH_RUN)
        unbroken = metres[i + FRESH_RUN - 1] - metres[i] == FRESH_RUN - 1
        if unbroken and (fresh[run] >= 0.5).all() and (kaolin[run] < 0.2).all():
            gap = float(metres[i] - metres[:i][kaolin[:i] >= 0.5].max() - 1)
            return {"m": float(metres[i]), "gap": gap} if gap <= MAX_GAP_M else None
    return None


def encode(table, groups, metres):
    """Rows of whole percentages in `groups` order, one per metre."""
    if table is None:
        return None
    grid = (table.reindex(index=metres, columns=groups) * 100).round().to_numpy()
    return [None if np.isnan(row).all() else [0 if v != v else int(v) for v in row] for row in grid]


def build() -> dict:
    logged = set(pd.read_csv(LOGGED, usecols=["hole_id"])["hole_id"].astype(str))
    level2 = level2_holes()
    parts = {}
    for path in sorted(TABLES.glob("*.csv")):
        columns = list(pd.read_csv(path, nrows=0, encoding="utf-8-sig").columns)
        wanted = [c for c in columns if c in ("hole_id", "depth_from_m")
                  or normalise(c).startswith(("grp", "min", "wt", "error", "snr"))]
        frame = pd.read_csv(path, usecols=wanted, encoding="utf-8-sig", low_memory=False)
        hole_id = str(frame["hole_id"].dropna().iloc[0]) if frame["hole_id"].notna().any() else ""
        if hole_id not in logged or not resolve_column(columns, ["grp1stsas", "grp1utsas"]):
            continue
        metre = pd.to_numeric(frame["depth_from_m"], errors="coerce").floordiv(1)
        order = channels(hole_id in level2)
        swir = fractions(frame, metre, columns, order["swir"])
        parts[hole_id] = {
            "swir": swir,
            "tir": fractions(frame, metre, columns, order["tir"]),
            "species": species(frame, metre, columns, order["swir"]),
            "q": quality(frame, metre, columns),
            "front": weathering_front(swir),
        }
        print(f"\r{len(parts)} holes", end="", flush=True)
    print()

    def order(kind):  # most common group first, so legends read in order
        totals = pd.concat([p[kind].sum() for p in parts.values() if p[kind] is not None], axis=1)
        return list(totals.sum(axis=1).sort_values(ascending=False).index)

    swir_groups, tir_groups = order("swir"), order("tir")
    holes = {}
    for hole_id, p in parts.items():
        known = [t.index for t in (p["swir"], p["tir"]) if t is not None] + [p["q"].index]
        first, last = int(min(i.min() for i in known)), int(max(i.max() for i in known))
        metres = np.arange(first, last + 1, dtype=float)
        q = p["q"].reindex(metres)
        names = None if p["species"] is None else p["species"].reindex(metres)
        holes[hole_id] = {
            "from": first,
            "swir": encode(p["swir"], swir_groups, metres),
            "tir": encode(p["tir"], tir_groups, metres),
            "species": None if names is None else [None if v != v else v for v in names.to_numpy()],
            "q": [None if v != v else int(v) for v in q.to_numpy()],
            "front": p["front"],
        }
    return {"swir_groups": swir_groups, "tir_groups": tir_groups, "holes": holes}


def check() -> None:
    """The two rules most likely to break quietly."""
    rows = ["KAOLIN"] * 8 + ["WHITE-MICA"] * 2 + ["CHLORITE"] * 6
    swir = pd.get_dummies(pd.Series(rows, index=np.arange(10.0, 26.0))).astype(float)
    assert weathering_front(swir) == {"m": 20.0, "gap": 2.0}, weathering_front(swir)
    assert weathering_front(swir.iloc[8:]) is None  # log starts in fresh rock
    frame = pd.DataFrame({"Grp1 sTSAS": ["CHLORITE", "INVALID"], "Wt1 sTSAS": [0.6, 0.9],
                          "Grp2 sTSAS": ["WHITE-MICA", None], "Wt2 sTSAS": [0.4, None]})
    shares = fractions(frame, pd.Series([0.0, 0.0]), list(frame.columns), CHANNELS["swir"]).iloc[0]
    assert shares.round(2).to_dict() == {"CHLORITE": 0.6, "WHITE-MICA": 0.4}, shares
    # the species comes from the winning group, even when another group's species is commoner
    frame = pd.DataFrame({"Grp1 sTSAS": ["CHLORITE"] * 4 + ["WHITE-MICA"] * 3 + ["INVALID"] * 5,
                          "Min1 sTSAS": ["Chlorite-Fe", "Chlorite-Mg", "Chlorite-Fe", "Chlorite-FeMg"]
                                        + ["Muscovite"] * 3 + ["Aspectral"] * 5})
    names = species(frame, pd.Series([0.0] * 12), list(frame.columns))
    assert names.to_dict() == {0.0: "Chlorite-Fe"}, names
    print("checks pass")


if __name__ == "__main__":
    if "--check" in sys.argv:
        check()
    else:
        payload = build()
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(payload, separators=(",", ":")))
        fronts = sum(h["front"] is not None for h in payload["holes"].values())
        tir = sum(h["tir"] is not None for h in payload["holes"].values())
        print(f"{len(payload['holes'])} holes, {tir} with a thermal view, {fronts} weathering "
              f"fronts -> {OUT.relative_to(ROOT)} ({OUT.stat().st_size / 1e6:.1f} MB)")
