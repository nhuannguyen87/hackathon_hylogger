"""
Add a holes.csv row for every hole the ETL pipeline produced (csv/wells/*.csv)
that isn't in holes.csv yet. Existing rows are never touched.

Run:  python data/make_holes_from_catalog.py

Collar, elevation, length, dip and azimuth come from the GSWA HyLogger catalog;
WAMEX confidentiality from the NVCL WA catalog. Both spreadsheets live in the
dataset-access folder next to this repo (override with --catalog-dir). Without
them, NVCL's own collars from etl.py's csv/holes.csv are used, drawn vertical.

measurements.csv is a separate step: download.py -> etl.py ->
files/extract.py -> data/build_measurements_from_wells.py.
"""

import argparse
import csv
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
CATALOG_DIR = HERE.parent.parent / "First Meeting & Dataset Access - RE_ GSWA HyLogger Capstone"

HOLE_FIELDS = ["hole_id", "hole_name", "latitude", "longitude", "easting", "northing",
               "elevation_m", "borehole_length_m", "inclination_deg", "azimuth_deg",
               "confidential"]
CATALOG_COLUMNS = {"Latitude (degrees)": "latitude", "Longitude (degrees)": "longitude",
                   "Easting": "easting", "Northing": "northing", "Elevation": "elevation_m",
                   "Total (m)": "borehole_length_m", "Inclination (dip)": "inclination_deg",
                   "Azimuth": "azimuth_deg"}


def catalog_rows(catalog_dir):
    gswa = pd.read_excel(catalog_dir / "gswa-hylogger-2026_07_06.xlsx")
    gswa["hole_id"] = gswa["Well Name and Info"].str.replace(r"\s*\[.*\]$", "", regex=True).str.strip()
    # ponytail: first catalog entry wins for the ~17 duplicated hole names
    gswa = gswa.drop_duplicates("hole_id").set_index("hole_id")[list(CATALOG_COLUMNS)]
    nvcl = pd.read_excel(catalog_dir / "NVCL_WA_Catalog.xlsx", header=1)
    status = dict(zip(nvcl["HoleName"].astype(str).str.strip(),
                      nvcl.iloc[:, 9].astype(str).str.strip()))
    return gswa.rename(columns=CATALOG_COLUMNS), status


def nvcl_rows():
    """No GSWA catalog: etl.py's csv/holes.csv (NVCL's own borehole records) -
    collar, elevation and length, no dip/azimuth, so holes draw vertical.
    load_interim later moves collars to DASC's GDA2020 positions."""
    nvcl = pd.read_csv(HERE / "csv" / "holes.csv", encoding="utf-8-sig", dtype={"hole_id": str})
    return nvcl.drop_duplicates("hole_id").set_index("hole_id")[["latitude", "longitude", "elevation_m", "borehole_length_m"]]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog-dir", type=Path, default=CATALOG_DIR)
    args = parser.parse_args()

    holes_csv = HERE / "holes.csv"
    have = {row["hole_id"] for row in csv.DictReader(holes_csv.open())} if holes_csv.exists() else set()
    logged = set()
    for path in (HERE / "csv" / "wells").glob("*.csv"):  # the id inside - file names are sanitised ("Brooke 1" -> Brooke_1)
        with path.open(encoding="utf-8-sig", newline="") as handle:
            first = next(csv.DictReader(handle), None)
        if first:
            logged.add(first["hole_id"])
    wanted = sorted(logged - have)

    if args.catalog_dir.is_dir():
        catalog, status = catalog_rows(args.catalog_dir)
    else:
        print(f"No GSWA catalog at {args.catalog_dir} - using NVCL collars from csv/holes.csv (drawn vertical)")
        catalog, status = nvcl_rows(), {}
    missing = [h for h in wanted if h not in catalog.index]
    rows = []
    for hole_id in wanted:
        if hole_id in missing:
            continue
        row = {k: ("" if pd.isna(v) else v) for k, v in catalog.loc[hole_id].items()}
        rows.append({"hole_id": hole_id, "hole_name": hole_id, **row,
                     "confidential": "true" if status.get(hole_id) == "CONFIDENTIAL" else "false"})

    new_file = not holes_csv.exists()
    with holes_csv.open("a", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=HOLE_FIELDS)
        if new_file:
            writer.writeheader()
        writer.writerows(rows)

    print(f"{len(rows)} holes added -> {holes_csv} ({len(have) + len(rows)} total)")
    if missing:
        print(f"not in the GSWA catalog, skipped: {', '.join(missing)}")


if __name__ == "__main__":
    main()
