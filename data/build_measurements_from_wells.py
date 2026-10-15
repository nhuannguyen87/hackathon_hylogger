"""
Step 5 (real data) - data/csv/wells/*.csv  ->  data/measurements.csv

Bridges files/extract.py's honest per-metre mineral+confidence calls into the
exact CSV shape backend/holes/management/commands/load_data.py expects. Run
this after download.py -> etl.py -> extract.py have produced
data/csv/wells/<hole_id>.csv for the holes you want loaded.

    python data/build_measurements_from_wells.py

What gets carried across, and what doesn't:
    mineral_1, mineral_1_pct   <- extract.py's dominant mineral group + its
                                   median weight for that metre (real)
    confidence, quality_flag   <- extract.py's multi-check confidence score
                                   (real - coverage, agreement, fit, SNR,
                                   dominance against this hole's own data)
    why                        <- extract.py's plain-English reason(s)
    mineral_2, mineral_2_pct   <- left blank. extract.py deliberately keeps
                                   only the single dominant call per metre
                                   ("the dumbest thing that could work"), so
                                   there's no real second mineral to report -
                                   inventing one would be exactly the kind of
                                   false confidence this project is about
                                   avoiding.
    band_wt / band_err / band_snr / band_coverage / band_agreement
                                <- extract.py's real per-metre quality
                                   numbers, prefixed band_ so load_data.py
                                   picks them up as anomaly-model features.
                                   This means the anomaly detector trains on
                                   genuine confidence-signal patterns, not
                                   raw spectral bands - those aren't in this
                                   scoped download (see download.py
                                   --scalars-only). Flags read as "this
                                   metre's quality signature is unusual",
                                   not "this mineralogy is unusual".
"""

import csv
from pathlib import Path

HERE = Path(__file__).resolve().parent
WELLS_DIR = HERE / "csv" / "wells"

QUALITY_FIELDS = ["wt", "err", "snr", "coverage", "agreement"]
OUT_FIELDS = (
    ["hole_id", "sample_no", "depth_from_m", "depth_to_m", "mineral_1", "mineral_1_pct",
     "mineral_2", "mineral_2_pct", "confidence", "quality_flag", "why"]
    + [f"band_{name}" for name in QUALITY_FIELDS]
)


def quality_flag_for(mineral, conf_class):
    if not mineral or mineral == "NO DATA":
        return "missing"
    if conf_class == "low":
        return "low_signal"
    return "ok"


def convert_hole(path):
    rows = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for sample_no, row in enumerate(csv.DictReader(handle), start=1):
            depth = float(row["depth"])
            mineral = row["mineral"].strip()
            row_out = {
                "hole_id": row["hole_id"],
                "sample_no": sample_no,
                "depth_from_m": depth,
                "depth_to_m": depth + 1.0,  # extract.py bins at 1 m (BIN)
                "mineral_1": "" if mineral == "NO DATA" else mineral,
                "mineral_1_pct": row.get("wt") or "",
                "mineral_2": "",
                "mineral_2_pct": "",
                "confidence": row.get("confidence") or 0.0,
                "quality_flag": quality_flag_for(mineral, row.get("conf_class")),
                "why": row.get("why") or "",
            }
            for name in QUALITY_FIELDS:
                row_out[f"band_{name}"] = row.get(name) or ""
            rows.append(row_out)
    return rows


def main():
    if not WELLS_DIR.is_dir():
        raise SystemExit(
            f"No {WELLS_DIR}. Run download.py, etl.py, then files/extract.py first."
        )

    all_rows = []
    hole_paths = sorted(WELLS_DIR.glob("*.csv"))
    if not hole_paths:
        raise SystemExit(f"No hole CSVs found in {WELLS_DIR}.")

    for path in hole_paths:
        all_rows.extend(convert_hole(path))

    out_path = HERE / "measurements.csv"
    with out_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUT_FIELDS)
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"{len(hole_paths)} holes, {len(all_rows)} measurement rows -> {out_path}")


if __name__ == "__main__":
    main()
