#!/usr/bin/env bash
# Build data/ from GSWA's open-file HyLogger data, fetched through NVCL's
# API (nvcl_kit, provider "wa"). Nothing here is committed - data/ is ignored.
#
#   ./get-data.sh                  the 20 holes in demo-holes.txt (~5 minutes)
#   ./get-data.sh my-holes.txt     any NVCL WA hole names, one per line
#
# Then ./setup.sh (first time) or ./reload-data.sh loads them.
set -e
cd "$(dirname "$0")"
[ -d .venv ] || { echo "No .venv yet - run ./setup.sh, which calls this for you."; exit 1; }
source .venv/bin/activate
HOLES="${1:-demo-holes.txt}"

python download.py --holes-file "$HOLES" --scalars-only --workers 4  # mineral scalars only, a few MB a hole
python etl.py                                   # -> data/csv/measurements/
python files/extract.py --out data              # -> per-metre mineral + confidence
python data/build_measurements_from_wells.py    # -> data/measurements.csv
python data/make_holes_from_catalog.py          # -> data/holes.csv
python data/build_derived.py                    # -> data/metres.json (mixes, species)
