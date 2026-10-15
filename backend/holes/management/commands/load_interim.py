"""
Load GSWA's DASC interim package ("HyLogger Drillhole Package") onto the
site's holes: company lab assays and logged rock, each hole's GSWA processing level,
commodity and document links, and its position - GDA2020, from whichever
two of DASC, the company collar (WAMEX/WAPIMS) and the NVCL catalog agree
(choose_position). Index holes the site doesn't have yet are added
(unlisted_holes), so a fresh clone shows every HyLogger hole from public
data alone.

    python manage.py load_interim
    python manage.py load_interim --dir /path/to/INTERIM_HyLogger_Dataset_Package_GDA2020_DB

The package's hylogger_dataset_index links each HyLogger hole to its WAMEX
CollarId(s) and gives its Level 1 / Level 2 release dates (Hole.catalog's
"gswa_level"); WAMEX_AssayFlatData holds the assay intervals. A site hole matches an
index row on Data_name, NVCL_HoleName or Hole_name (its own id first, then
without a " [chips]"-style suffix - never for "[dup. name]" or "[wedge]");
every collar of every matching row counts, except that rows more than
0.5 km apart are namesakes and only those nearest the hole count (own_rows).
Below-detection codes, implausible values and zero-length intervals are
handled as holes/assays.py describes. Safe to re-run: it replaces all assays.
"""

import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from holes.assays import ELEMENTS, classify
from holes.minerals import commodity_codes
from holes.models import Assay, Geology, Hole

sys.path.insert(0, str(settings.PROJECT_ROOT))  # nvcl_datasets.py lives at the project root
from nvcl_datasets import SAME_HOLE_KM, distance_km  # noqa: E402

PACKAGE = "INTERIM_HyLogger_Dataset_Package_GDA2020_DB"
BATCH = 5000


def same_hole_name(hole_id):
    """'00KE16 [chips]' -> '00KE16': the suffix names part of the same hole. A
    '[dup. name]' (a namesake elsewhere) or '[wedge...]' (another path) keeps
    its full name - it must never borrow the parent's or namesake's data."""
    match = re.search(r"\s*\[(.*)\]$", hole_id)
    if not match or re.search(r"dup|wedge", match.group(1), re.IGNORECASE):
        return hole_id
    return hole_id[:match.start()].strip()


def point(lat, lon):
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return None
    return (lat, lon) if lat and lon and abs(lat) <= 90 and abs(lon) <= 180 else None


def choose_position(nvcl, dasc, company, same_km=SAME_HOLE_KM):
    """The position two sources agree on, as (lat, lon, source, note).

    DASC's GDA2020 position wins unless the company's own collar sides with
    the NVCL catalog instead (RKD005: DASC has a 6-degree longitude typo).
    A note says so whenever a source is more than `same_km` away."""
    far = lambda a, b: distance_km(a, b) > same_km  # noqa: E731
    km = lambda a, b: f"{distance_km(a, b):,.1f} km"  # noqa: E731
    if company and far(dasc, company) and not far(nvcl, company):
        return (*nvcl, "NVCL catalog", f"GSWA's DASC position is {km(dasc, company)} from the company collar; "
                                        "kept the NVCL catalog position, which matches it.")
    if not far(nvcl, dasc):
        note = (f"The company collar is {km(dasc, company)} away; the NVCL catalog and GSWA's DASC position "
                "agree." if company and far(dasc, company) else None)
        return (*dasc, "DASC GDA2020", note)
    if company and not far(dasc, company):
        return (*dasc, "DASC GDA2020", f"Moved {km(nvcl, dasc)}: the NVCL catalog had it there; GSWA's DASC "
                                       "position and the company collar agree.")
    detail = f"the company collar is {km(dasc, company)} away" if company else "no company collar to check"
    return (*dasc, "DASC GDA2020", f"The NVCL catalog and GSWA's DASC position are {km(nvcl, dasc)} apart "
                                   f"({detail}); showing DASC's.")


def own_rows(entries, nvcl, same_km=SAME_HOLE_KM):
    """The index rows that are this hole. Rows more than `same_km` apart are
    namesakes (BH01 and BH01_Behemoth, 1,250 km away): only those nearest
    the hole's NVCL position count - for its assays, level and position."""
    located = [e for e in entries if e["dasc"]]
    if not located or max(distance_km(a["dasc"], b["dasc"]) for a in located for b in located) <= same_km:
        return entries
    nearest = min(located, key=lambda e: distance_km(nvcl, e["dasc"]))
    return [e for e in located if distance_km(nearest["dasc"], e["dasc"]) <= same_km]


def released(value):
    return isinstance(value, str) and value.strip() and value.strip().upper() != "NULL"


def collar_ids(value):
    """'3191022' / '3663110, 3663111' / NaN / 'NULL' -> ['3191022'] / [...] / []"""
    return [c.strip() for c in re.split(r"[,;]", str(value)) if c.strip() and c.strip().upper() not in ("NAN", "NULL")]


def number(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if value == value else None  # NaN


def keyed(table, key):
    table[key] = table[key].astype(str).str.strip()
    return table.drop_duplicates(key).set_index(key)


def index_entry(row, wamex, wapims, top):
    """One HyLogger_Dataset_Index row, with the company's collar for it:
    WAMEX for mineral holes, WAPIMS for petroleum wells."""
    ids = collar_ids(row.WAMEX_CollarId)
    found = [c for c in ids if c in wamex.index and point(wamex.at[c, "Latitude"], wamex.at[c, "Longitude"])]
    well = str(row.WAPIMS_report_Wnumber).strip()
    if found:
        rec = wamex.loc[found[0]]
        collar, elevation, length = point(rec.Latitude, rec.Longitude), rec.Elevation, rec.MaxDepth
    elif well in wapims.index:
        rec = wapims.loc[well]
        collar, elevation, length = point(rec.Latitude, rec.Longitude), rec.GroundElevation, rec.DrillersTD
    else:
        collar = elevation = length = None
    station = top.loc[found[0]] if found and found[0] in top.index else None
    links = {key: url for key, url in [("tray_images", row.MOSAIC), ("summary_histogram", row.SUM_HISTO),
                                       ("summary_report", row.SUM_REPORT), ("summary_mineral_logs", row.MINERALLOG)]
             if isinstance(url, str) and url.startswith("http")}
    return {
        "names": [n.strip() for n in (row.NVCL_HoleName, row.Hole_name, row.Data_name) if isinstance(n, str) and n.strip()],
        "collars": ids + collar_ids(row.WAMEX_CollarId_alternate),
        "level": (({"level": 2, "released": row.LEV2_REL_D} if released(row.LEV2_REL_D) else None)
                  or ({"level": 1, "released": row.LEV1_REL_D} if released(row.LEV1_REL_D) else None)),
        "dasc": point(row.Shapefile_latitude, row.Shapefile_longitude),
        "company": collar,
        "catalog": {key: value for key, value in [
            ("commodity", commodity_codes(row.COMMODITY)),
            ("project", row.PROJECT.strip() if isinstance(row.PROJECT, str) else ""), ("links", links)] if value},
        # what a hole the site doesn't have yet is drawn with
        "hole": {"elevation_m": number(elevation), "borehole_length_m": number(length),
                 "inclination_deg": number(station.Dip) if station is not None else None,
                 "azimuth_deg": number(station.Azimuth) if station is not None else None,
                 "confidential": str(row.Confidentiality_primary_Anumber).upper().startswith("CONF")},
    }


def nvcl_position(hole):
    """The NVCL catalog position: where load_data left the hole, unless this
    command moved it last run ("at") - so re-runs agree."""
    placed = (hole.catalog or {}).get("position") or {}
    here = [hole.latitude, hole.longitude]
    return tuple(placed["nvcl"] if placed.get("at") == here else here)


def unlisted_holes(rows_of, holes, claimed):
    """New Holes for index rows no site hole claims or shares a name with - on
    a fresh clone, every HyLogger hole but the pipeline's few. Positioned by
    DASC, drawn from the company's collar and first survey station."""
    taken = {hole.hole_id for hole in holes}
    known = taken | {same_hole_name(h) for h in taken}
    new = []
    for entry in {id(e): e for entries in rows_of.values() for e in entries}.values():
        if id(entry) in claimed or not entry["dasc"] or known & set(entry["names"]):
            continue
        if any(h.hole_id in entry["names"] and distance_km((h.latitude, h.longitude), entry["dasc"]) <= SAME_HOLE_KM
               for h in new):
            continue  # another dataset of a hole just added
        name = next((n for n in entry["names"] if n not in taken), None)
        if name:
            taken.add(name)
            new.append(Hole(hole_id=name, hole_name=name, latitude=entry["dasc"][0], longitude=entry["dasc"][1],
                            **{k: v for k, v in entry["hole"].items() if v is not None}))
    return new


class Command(BaseCommand):
    help = "Load the DASC interim package: WAMEX assays and logged rock, GSWA processing levels, GDA2020 positions."

    def add_arguments(self, parser):
        parser.add_argument("--dir", default=str(settings.PROJECT_ROOT / PACKAGE),
                            help="The unzipped interim package folder")

    def handle(self, *args, **options):
        csv_dir = Path(options["dir"]) / "DATABASES" / "CSV"
        if not csv_dir.is_dir():
            raise SystemExit(f"No {csv_dir}. Download the HyLogger Drillhole Package from DASC "
                             "(https://dasc.dmirs.wa.gov.au/) and unzip it into the project folder.")

        index = pd.read_csv(csv_dir / "HyLogger_Dataset_Index.csv", encoding="utf-8-sig", dtype=str)
        survey = pd.read_csv(csv_dir / "WAMEX_Survey.csv", encoding="utf-8-sig", dtype=str)
        survey["Depth"] = pd.to_numeric(survey.Depth, errors="coerce")
        company = {"wamex": keyed(pd.read_csv(csv_dir / "WAMEX_Collar.csv", encoding="utf-8-sig", dtype=str), "CollarId"),
                   "wapims": keyed(pd.read_csv(csv_dir / "WAPIMS_Collar.csv", encoding="utf-8-sig", dtype=str), "WellId"),
                   "top": keyed(survey.sort_values("Depth"), "CollarId")}  # each collar's first survey station
        rows_of = defaultdict(list)  # index name -> its rows
        for row in index.itertuples():
            entry = index_entry(row, **company)
            for name in set(entry["names"]):
                rows_of[name].append(entry)

        def rows(hole):
            return own_rows(rows_of.get(hole.hole_id) or rows_of.get(same_hole_name(hole.hole_id)) or [],
                            nvcl_position(hole))

        holes = list(Hole.objects.all())
        new = unlisted_holes(rows_of, holes, {id(e) for hole in holes for e in rows(hole)})
        Hole.objects.bulk_create(new, batch_size=1000)

        hole_of, changed, counts = {}, [], Counter()  # collar id -> site hole id
        for hole in holes + new:
            catalog = dict(hole.catalog or {})
            here = [hole.latitude, hole.longitude]
            nvcl = nvcl_position(hole)
            catalog.pop("position", None)
            hole.latitude, hole.longitude = nvcl
            entries = rows(hole)
            for entry in entries:
                for collar in entry["collars"]:
                    hole_of.setdefault(collar, hole.hole_id)
                # commodity, project, document links: GSWA's catalog spreadsheet's win
                for key, value in entry["catalog"].items():
                    catalog[key] = {**value, **catalog.get(key, {})} if key == "links" else catalog.get(key) or value
            # NVCL's own record has no dip, azimuth or elevation: a hole GSWA's
            # catalog spreadsheet didn't describe takes the company's
            drawn = (hole.inclination_deg, hole.azimuth_deg, hole.elevation_m, hole.borehole_length_m)
            reported = next((e["hole"] for e in entries if e["hole"]["inclination_deg"] is not None),
                            entries[0]["hole"] if entries else None)
            if reported and "location" not in catalog:
                if (hole.inclination_deg, hole.azimuth_deg) == (-90.0, 0.0) and reported["inclination_deg"] is not None:
                    hole.inclination_deg, hole.azimuth_deg = reported["inclination_deg"], reported["azimuth_deg"] or 0.0
                hole.elevation_m = hole.elevation_m if hole.elevation_m is not None else reported["elevation_m"]
                hole.borehole_length_m = hole.borehole_length_m or reported["borehole_length_m"]
            levels = [e["level"] for e in entries if e["level"]]
            level = max(levels, key=lambda lv: lv["level"]) if levels else None
            if level:
                catalog["gswa_level"] = level
            else:
                catalog.pop("gswa_level", None)  # e.g. a namesake's level from an earlier run
            counts["levelled"] += bool(level)

            located = [e["dasc"] for e in entries if e["dasc"]]
            if located:
                collar = next((e["company"] for e in entries if e["company"]), None)
                dasc = min(located, key=lambda p: distance_km(collar or nvcl, p))
                lat, lon, source, note = choose_position(nvcl, dasc, collar)
                catalog["position"] = {"source": source, "note": note, "nvcl": list(nvcl), "at": [lat, lon]}
                counts[source] += 1
                counts["noted"] += bool(note)
                hole.latitude, hole.longitude = lat, lon
            if (catalog != hole.catalog or here != [hole.latitude, hole.longitude]
                    or drawn != (hole.inclination_deg, hole.azimuth_deg, hole.elevation_m, hole.borehole_length_m)):
                hole.catalog = catalog
                changed.append(hole)
        Hole.objects.bulk_update(changed, ["catalog", "latitude", "longitude", "inclination_deg", "azimuth_deg",
                                           "elevation_m", "borehole_length_m"], batch_size=1000)
        self.stdout.write(f"{len(new)} holes added from GSWA's index (not on the site yet). GSWA processing level on "
                          f"{counts['levelled']} holes. Positions: {counts['DASC GDA2020']} from DASC (GDA2020), "
                          f"{counts['NVCL catalog']} kept from the NVCL catalog where DASC disagreed with the company "
                          f"collar; {counts['noted']} carry a note.")

        columns = ["CollarId", "FromDepth", "ToDepth", *ELEMENTS.values()]
        table = pd.read_csv(csv_dir / "WAMEX_AssayFlatData.csv", encoding="utf-8-sig", usecols=columns,
                            na_values=["NULL"], dtype={"CollarId": str}, low_memory=False)
        table = table[table.CollarId.isin(hole_of)]
        table["FromDepth"] = pd.to_numeric(table.FromDepth, errors="coerce")
        table["ToDepth"] = pd.to_numeric(table.ToDepth, errors="coerce")
        bad_length = int((~(table.ToDepth > table.FromDepth)).sum())
        table = table[table.ToDepth > table.FromDepth]

        counts = Counter()
        rows = []
        for record in table.itertuples(index=False):
            values, below, suspect = {}, [], {}
            for element, column in ELEMENTS.items():
                kind, value = classify(element, getattr(record, column))
                if kind == "value":
                    values[element] = round(float(value), 6)
                elif kind == "below_detection":
                    below.append(element)
                elif kind == "suspect":
                    suspect[element] = float(value)
                    counts[f"suspect {element}"] += 1
            if values or below or suspect:
                rows.append(Assay(hole_id=hole_of[record.CollarId], depth_from_m=record.FromDepth,
                                  depth_to_m=record.ToDepth, values=values, below_detection=below,
                                  suspect=suspect, collar_id=record.CollarId))
        with transaction.atomic():
            Assay.objects.all().delete()
            Assay.objects.bulk_create(rows, batch_size=BATCH)

        holes = len({r.hole_id for r in rows})
        self.stdout.write(f"{len(rows):,} assay intervals on {holes} site holes "
                          f"({len(hole_of)} WAMEX collars matched; {bad_length} zero/negative-length intervals dropped).")
        if counts:
            self.stdout.write("Set aside as suspect units: " + ", ".join(f"{k.split()[1]} {n}" for k, n in counts.most_common()))
        self.load_geology(csv_dir, hole_of)

    def load_geology(self, csv_dir, hole_of):
        """The rock each company logged (WAMEX_DHGeology), for holes/geology.py."""
        table = pd.read_csv(csv_dir / "WAMEX_DHGeology.csv", encoding="utf-8-sig", dtype=str,
                            usecols=["CollarId", "FromDepth", "ToDepth", "CompanyLithologyCodeMerged",
                                     "CompanyLithologyName", "GSWARockName", "GSWARegolithName"])
        table = table[table.CollarId.isin(hole_of)].copy()
        table["FromDepth"] = pd.to_numeric(table.FromDepth, errors="coerce")
        table["ToDepth"] = pd.to_numeric(table.ToDepth, errors="coerce")
        table = table[table.ToDepth > table.FromDepth].fillna("")
        rows = []
        for r in table.itertuples(index=False):
            code, name = r.CompanyLithologyCodeMerged.strip(), r.CompanyLithologyName.strip()
            rock = (r.GSWARockName or r.GSWARegolithName).strip()
            if code or name or rock:
                rows.append(Geology(hole_id=hole_of[r.CollarId], depth_from_m=r.FromDepth, depth_to_m=r.ToDepth,
                                    code=code[:64], name=name[:255], rock=rock[:128], collar_id=r.CollarId))
        with transaction.atomic():
            Geology.objects.all().delete()
            Geology.objects.bulk_create(rows, batch_size=BATCH)
        named = sum(bool(r.rock or r.name) for r in rows)
        self.stdout.write(f"{len(rows):,} logged-rock intervals on {len({r.hole_id for r in rows})} site holes "
                          f"({named:,} with a rock name; the rest carry a company code only).")
