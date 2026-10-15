"""
Load two GSWA spreadsheets for the Minerals tab:

    gswa-hylogger-*.xlsx            per hole: commodity, project, processing level,
                                    sample type, location and the five document
                                    links (Drill Report, Summary Report, Summary
                                    Histogram, Tray Images, Summary Mineral Logs)
                                    -> Hole.catalog
    Hylogger_vocab_working_*.xlsx   GSWA's HyLogger vocabulary -> VocabTerm

    python manage.py load_gswa_catalog
    python manage.py load_gswa_catalog --dir "/path/to/the/dataset-access/folder"

The links are cell hyperlinks, so the catalog is read with openpyxl (pandas
drops them). A hole matches on its full "Well Name and Info" first - 327 site
holes are named that way, " [chips]" suffix and all - then on the name minus
that suffix. A name listed more than once has its commodities merged and
keeps the first value given for everything else. Safe to re-run.
"""

import re
from pathlib import Path

import openpyxl
import pandas as pd
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from holes.minerals import commodity_codes
from holes.models import Hole, VocabTerm

FOLDER = "First Meeting & Dataset Access - RE_ GSWA HyLogger Capstone"
# the dataset-access folder beside the project folder, or one level further up
DEFAULT_DIRS = [settings.PROJECT_ROOT.parent / FOLDER, settings.PROJECT_ROOT.parent.parent / FOLDER]

LINK_COLUMNS = {
    "Drill Report": "drill_report", "Summary Report": "summary_report",
    "Summary Histogram": "summary_histogram", "Tray Images": "tray_images",
    "Summary Mineral Logs": "summary_mineral_logs",
}
TEXT_COLUMNS = {"Project": "project", "Process Level": "process_level", "TYPE": "type", "Location": "location"}


def newest(folder, pattern):
    found = sorted(folder.glob(pattern))
    if not found:
        raise SystemExit(f"No {pattern} in {folder}.")
    return found[-1]


def text(value):
    if value is None or (isinstance(value, float) and value != value):
        return ""
    return str(value).strip()


def link(cell):
    if cell.hyperlink and cell.hyperlink.target:
        return cell.hyperlink.target
    value = text(cell.value)
    return value if value.startswith("http") else ""


class Command(BaseCommand):
    help = "Load the GSWA HyLogger catalog (commodity, links) and vocabulary for the Minerals tab."

    def add_arguments(self, parser):
        parser.add_argument("--dir", default=None, help="Folder holding the two GSWA spreadsheets")

    def handle(self, *args, **options):
        if options["dir"]:
            folder = Path(options["dir"])
        else:
            folder = next((d for d in DEFAULT_DIRS if d.is_dir()), None)
            if folder is None:
                raise SystemExit(f"Can't find '{FOLDER}'. Pass --dir.")
        self.load_catalog(newest(folder, "gswa-hylogger-*.xlsx"))
        self.load_vocab(newest(folder, "Hylogger_vocab*.xlsx"))

    @transaction.atomic
    def load_catalog(self, path):
        sheet = openpyxl.load_workbook(path).active  # not read_only: that drops hyperlinks
        rows = sheet.iter_rows()
        column = {text(cell.value): i for i, cell in enumerate(next(rows))}

        def merge(entries, name, row):
            entry = entries.setdefault(name, {"commodity": [], "links": {}})
            for code in commodity_codes(row[column["Commodity"]].value):
                if code not in entry["commodity"]:
                    entry["commodity"].append(code)
            for title, key in TEXT_COLUMNS.items():
                if not entry.get(key):
                    entry[key] = text(row[column[title]].value)
            for title, key in LINK_COLUMNS.items():
                if not entry["links"].get(key):
                    entry["links"][key] = link(row[column[title]])

        by_name, by_base = {}, {}  # "00KE16 [chips]" / "00KE16"
        for row in rows:
            name = text(row[column["Well Name and Info"]].value)
            if not name:
                continue
            merge(by_name, name, row)
            merge(by_base, re.sub(r"\s*\[.*\]$", "", name).strip(), row)

        holes = list(Hole.objects.all())
        matched = []
        for hole in holes:
            entry = by_name.get(hole.hole_id) or by_base.get(hole.hole_id)
            if entry:
                # merged: gswa_level / position belong to load_interim
                hole.catalog = {**(hole.catalog or {}), **entry, "links": {k: v for k, v in entry["links"].items() if v}}
                matched.append(hole)
        Hole.objects.bulk_update(matched, ["catalog"], batch_size=1000)
        self.stdout.write(
            f"{path.name}: {len(by_name)} catalog entries, {len(matched)} of the site's "
            f"{len(holes)} holes matched ({len(holes) - len(matched)} not in the catalog by name)."
        )

    @transaction.atomic
    def load_vocab(self, path):
        # one concept per row from row 4; columns: IRI, label, definition, alt labels, broader
        sheet = pd.read_excel(path, header=None).iloc[3:]
        terms, seen = [], set()
        for order, (_, row) in enumerate(sheet.iterrows()):
            label = text(row[1])
            if not label:
                continue
            slug = text(row[0]) or slugify(label) or label.lower()
            if slug in seen:
                continue
            seen.add(slug)
            terms.append(VocabTerm(
                slug=slug, label=label, definition=text(row[2]),
                alt_labels=", ".join(part.strip() for part in re.split(r"[\n,]", text(row[3])) if part.strip()),
                broader=text(row[4]), order=order,
            ))
        VocabTerm.objects.all().delete()
        VocabTerm.objects.bulk_create(terms)
        self.stdout.write(f"{path.name}: {len(terms)} vocabulary terms.")
