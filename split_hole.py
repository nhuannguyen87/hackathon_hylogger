#!/usr/bin/env python
"""Split a data/raw/<hole> folder that holds more than one hole's NVCL data.

NVCL answers a hole id with every dataset filed under it, ignoring case, and
some ids cover two different holes: "BH01" is a 3.6 m Bunbury bore (dataset
"BH01") and a Behemoth hole 1,250 km away (dataset "BH01_Behemoth").
download.py wrote both into one folder, so data/raw/BH01, BH02, BBDD0001,
BBDD0002, MWDD001 and MWDD002 each hold two holes. This moves every dataset
that isn't the folder's own hole (core_strip.hole_datasets decides) into
data/raw/<its dataset name>/, with its share of every manifest, so each
folder is one hole again and its name is the hole's id everywhere after it
(etl.py, core_strip.py, the holes table).

Which log belongs to which dataset comes from the getDatasetCollection
response download.py cached under data/.cache/<provider>/<hole>/, so this
runs offline. borehole.json goes with the hole it describes (NVCL's WFS
returns either hole's record for a shared id); the other folder gets one
built from its dataset's TSG header, and says so in "split_note".

    python split_hole.py BH01            # show what would move
    python split_hole.py BH01 --apply    # move it
"""

from __future__ import annotations

import argparse
import math
import os
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import atomic_write_json, read_json, utc_now  # noqa: E402
from core_strip import hole_datasets  # noqa: E402
from nvcl_datasets import SAME_HOLE_KM, distance_km, header_collar, lat_lon  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
CACHE_DIR = PROJECT_ROOT / "data" / ".cache"

# download.py's per-log files, and where the log id sits in each path.
LOG_FILE_PATTERNS = [
    re.compile(r"^(?:scalars|spectral|profilometer|mosaics)/(?P<log>[^_/]+)_"),
    re.compile(r"^images/tray_(?P<log>[^_/]+)_[^/]+$"),
    re.compile(r"^images/(?:tray_image|imagery)/(?P<log>[^/]+)(?:/|$)"),
]


def dataset_collection(folder: Path, provider: str) -> ET.Element:
    """The getDatasetCollection response download.py cached for this hole."""
    matches = sorted((CACHE_DIR / provider / folder.name).glob("*getDatasetCollection*"))
    if not matches:
        raise FileNotFoundError(f"no cached getDatasetCollection response under {CACHE_DIR / provider / folder.name}")
    return ET.fromstring(matches[0].read_text(encoding="utf-8", errors="replace"))


def log_owners(root: ET.Element) -> tuple[dict[str, str], dict[str, tuple[float, float]]]:
    """({log id: dataset id} for every log in every dataset, {dataset id: DepthRange})."""
    owners, depths = {}, {}
    for dataset in root.findall("./Dataset"):
        dataset_id = dataset.findtext("DatasetID") or ""
        for element in dataset.iter():
            if element.tag in ("LogID", "logID") and element.text:
                owners[element.text.strip()] = dataset_id
        try:
            depths[dataset_id] = (float(dataset.findtext("DepthRange/start")), float(dataset.findtext("DepthRange/end")))
        except (TypeError, ValueError):
            pass
    return owners, depths


def file_log_id(relative: str) -> str | None:
    for pattern in LOG_FILE_PATTERNS:
        match = pattern.match(relative)
        if match:
            return match.group("log")
    return None


def plan_split(folder: Path, provider: str) -> dict:
    """Everything a split would do, without touching the folder."""
    datasets = read_json(folder / "datasets.json")
    own_ids = {item["dataset_id"] for item in hole_datasets(folder, folder.name)}
    others = [item for item in datasets if item["dataset_id"] not in own_ids]

    # Other holes: each foreign dataset, plus any other foreign dataset at its
    # collar (a chips run of that hole), goes to data/raw/<its dataset name>.
    targets: dict[str, list[dict]] = {}
    for item in others:
        if any(item in group for group in targets.values()):
            continue
        collar = header_collar(item)
        targets[item["dataset_name"]] = [
            other for other in others
            if other is item or (collar and (km := distance_km(header_collar(other), collar)) is not None
                                 and km <= SAME_HOLE_KM)
        ]
    for name in targets:
        if not re.fullmatch(r"[A-Za-z0-9._-]+", name) or (RAW_DIR / name).exists() or name == folder.name:
            raise ValueError(f"can't split into data/raw/{name}: not a plain folder name, or it already exists")

    owners, depths = log_owners(dataset_collection(folder, provider))
    dataset_hole = {item["dataset_id"]: folder.name for item in datasets if item["dataset_id"] in own_ids}
    dataset_hole.update({item["dataset_id"]: name for name, group in targets.items() for item in group})
    missing = [item["dataset_name"] for item in datasets if item["dataset_id"] not in set(owners.values())]
    if missing:
        raise ValueError(f"cached getDatasetCollection has no logs for {missing} - re-download before splitting")

    moves, unattributed = [], []
    for path in sorted(folder.rglob("*")):
        relative = path.relative_to(folder).as_posix()
        if "/" not in relative:
            continue  # top-level metadata is rewritten, not moved
        log_id = file_log_id(relative)
        hole = dataset_hole.get(owners.get(log_id, ""))
        if hole is None:
            if path.is_file():
                unattributed.append(relative)
        elif hole != folder.name and not any(relative.startswith(f"{moved}/") for _, moved in moves):
            if path.is_dir() and log_id in relative.split("/")[-1]:
                moves.append((hole, relative))  # a whole per-log image folder
            elif path.is_file():
                moves.append((hole, relative))
    return {
        "datasets": datasets, "dataset_hole": dataset_hole, "owners": owners, "depths": depths,
        "targets": targets, "moves": moves, "unattributed": unattributed,
    }


def keep(entries, hole: str, plan: dict, key: str = "log_id"):
    """The entries of a download.py metadata list that belong to `hole`,
    by each entry's log_id (via its dataset) or its dataset_id."""
    def dataset_of(entry: dict) -> str:
        value = str(entry.get(key) or "")
        return plan["owners"].get(value, "") if key == "log_id" else value
    return [entry for entry in entries if plan["dataset_hole"].get(dataset_of(entry)) == hole]


def nonzero(value: object) -> float | None:
    """A float, or None for a blank - TSG writes 0 for a field it doesn't know."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number else None


def borehole_holder(borehole: dict, plan: dict) -> str | None:
    """Which hole borehole.json describes: the one whose dataset it names,
    else the one whose TSG header collar it sits at."""
    for item in plan["datasets"]:
        if item.get("dataset_name") == borehole.get("name"):
            return plan["dataset_hole"][item["dataset_id"]]
    collar = lat_lon(borehole.get("y"), borehole.get("x"))
    for item in plan["datasets"]:
        km = distance_km(collar, header_collar(item))
        if km is not None and km <= SAME_HOLE_KM:
            return plan["dataset_hole"][item["dataset_id"]]
    return None


def header_borehole(dataset: dict, nvcl_id: str, depth: tuple[float, float] | None, described: str) -> dict:
    """A borehole.json for a hole NVCL's WFS record didn't describe, from what
    its own dataset records - the same keys download.py's WFS record has."""
    try:
        header = ET.fromstring(str(dataset.get("description") or "<x/>"))
    except ET.ParseError:
        header = ET.Element("x")
    lat, lon = header_collar(dataset) or (None, None)
    rl = nonzero(header.findtext("RL"))
    record = dict.fromkeys(
        ["description", "purpose", "drillingMethod", "operator", "driller", "drillStartDate", "drillEndDate",
         "startPoint", "inclinationType", "boreholeMaterialCustodian", "elevation_srs", "positionalAccuracy",
         "source", "parentBorehole_uri", "metadata_uri", "genericSymbolizer", "tenement"], "")
    record.update({
        "nvcl_id": nvcl_id, "x": lon, "y": lat, "z": 0.0,
        "href": dataset.get("borehole_uri", ""), "identifier": dataset.get("borehole_uri", ""),
        "name": dataset["dataset_name"], "status": "unknown",
        "boreholeLength_m": f"{depth[1] - depth[0]:g}" if depth else "",
        "elevation_m": f"{rl:g}" if rl else "",
        "project": (header.findtext("Project") or "").strip(),
        "split_note": (f"Built by split_hole.py from NVCL dataset {dataset['dataset_id']}'s TSG header: "
                       f"NVCL's WFS record for {nvcl_id} described {described}."),
    })
    return record


LOG_LISTS = ("logs_scalar.json", "logs_image.json", "logs_spectral.json", "logs_profilometer.json",
             "scalar_manifest.json", "spectral_manifest.json", "profilometer_manifest.json")
DATASET_LISTS = ("image_logs_by_dataset.json",)


def apply_split(folder: Path, plan: dict) -> None:
    # Every original is read before anything is written - the folder's own
    # copies get overwritten with its share below.
    original = {path.name: read_json(path) for path in folder.glob("*.json")}
    borehole = original["borehole.json"]
    holder = borehole_holder(borehole, plan)

    for hole in plan["targets"]:
        (RAW_DIR / hole).mkdir()
    for hole, relative in plan["moves"]:
        target = RAW_DIR / hole / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(folder / relative, target)

    for hole in [folder.name, *plan["targets"]]:
        def write(name: str, value) -> None:
            atomic_write_json(RAW_DIR / hole / name, value)

        datasets = [item for item in plan["datasets"] if plan["dataset_hole"][item["dataset_id"]] == hole]
        write("datasets.json", datasets)
        for name in LOG_LISTS:
            if name in original:
                write(name, keep(original[name], hole, plan))
        for name in DATASET_LISTS:
            if name in original:
                write(name, keep(original[name], hole, plan, key="dataset_id"))
        if "images_manifest.json" in original:
            images = original["images_manifest.json"]
            write("images_manifest.json", {
                "logs": keep(images.get("logs", []), hole, plan, key="dataset_id"),
                "files": keep(images.get("files", []), hole, plan, key="dataset_id"),
            })
        if "tray_depths.json" in original:
            write("tray_depths.json", {
                log_id: rows for log_id, rows in original["tray_depths.json"].items()
                if plan["dataset_hole"].get(plan["owners"].get(log_id, "")) == hole
            })
        if hole == holder:
            write("borehole.json", borehole)
        else:
            anchor = next((item for item in datasets if item["dataset_name"] == hole), datasets[0])
            write("borehole.json", header_borehole(
                anchor, str(borehole.get("nvcl_id") or folder.name),
                plan["depths"].get(anchor["dataset_id"]), holder or "neither hole"))
        write("package_manifest.json", {
            **original.get("package_manifest.json", {}), "hole_id": hole, "content_fingerprint": None,
            "split": {"at": utc_now(), "from": folder.name, "datasets": [item["dataset_name"] for item in datasets],
                      "note": "split_hole.py moved each hole's datasets into its own folder; the rest of this "
                              "manifest describes the original download of " + folder.name},
        })


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("hole", help="data/raw folder to split, e.g. BH01")
    parser.add_argument("--provider", default="wa", help="NVCL provider the download used (default wa)")
    parser.add_argument("--apply", action="store_true", help="move the files (default: only show the plan)")
    args = parser.parse_args()

    folder = RAW_DIR / args.hole
    plan = plan_split(folder, args.provider)
    if not plan["targets"]:
        print(f"{args.hole}: every dataset is this hole's - nothing to split")
        return 0
    for item in plan["datasets"]:
        print(f"  dataset {item['dataset_name']:<24} -> data/raw/{plan['dataset_hole'][item['dataset_id']]}")
    moved = Counter(hole for hole, _ in plan["moves"])
    for hole, count in moved.items():
        print(f"  {count} files/folders -> data/raw/{hole}")
    if plan["unattributed"]:
        print(f"  {len(plan['unattributed'])} files with no known log stay put, e.g. {plan['unattributed'][:3]}")
    if not args.apply:
        print("dry run - pass --apply to move them")
        return 0
    apply_split(folder, plan)
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
