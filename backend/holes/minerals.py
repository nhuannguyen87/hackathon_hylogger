"""
What the Minerals tab needs: every mineral in every hole, by its everyday
name, most valuable (commodities) or rarest (detected minerals) first.

Two kinds of "mineral", kept apart on purpose:

  commodity  what a hole was drilled FOR - the GSWA catalog's "Commodity"
             (Au, Cu, ...). HyLogger never sees gold, silver or copper
             themselves: metals have no infrared signature. So "Gold" here
             means "drilled for gold", never "gold detected".
  group      what HyLogger DETECTED - Measurement.mix (SWIR + TIR shares),
             with Measurement.mineral_1_species as the specific mineral.
"""

import re
from collections import Counter

from django.core.cache import cache
from django.db.models import Count, Max

from . import assays
from .models import Hole, Measurement, VocabTerm

# Most valuable first. ponytail: a fixed ranking by rough price per kg (then
# strategic value, then energy/other), not live prices - reorder here.
COMMODITIES = [
    ("PGE", "Platinum-group metals"), ("PT", "Platinum"), ("PD", "Palladium"),
    ("AU", "Gold"), ("DIAMOND", "Diamond"), ("AG", "Silver"),
    ("DY", "Dysprosium"), ("HREE", "Heavy rare earths"), ("ND", "Neodymium"),
    ("PR", "Praseodymium"), ("REE", "Rare-earth elements"), ("CE", "Cerium"),
    ("TA", "Tantalum"), ("CS", "Caesium"), ("U", "Uranium"), ("LI", "Lithium"),
    ("CO", "Cobalt"), ("SN", "Tin"), ("W", "Tungsten"), ("MO", "Molybdenum"),
    ("NB", "Niobium"), ("V", "Vanadium"), ("NI", "Nickel"), ("CU", "Copper"),
    ("GRAPHITE", "Graphite"), ("HG", "Mercury"), ("ZN", "Zinc"), ("PB", "Lead"),
    ("BASE METALS", "Base metals"), ("CR", "Chromium"), ("MN", "Manganese"),
    ("ZR", "Zircon"), ("TI", "Titanium"), ("FE", "Iron ore"), ("AL", "Aluminium"),
    ("BA", "Barite"), ("F", "Fluorite"), ("ANDALUSITE", "Andalusite"),
    ("GARNET", "Garnet"), ("TALC", "Talc"), ("POTASH", "Potash"), ("SALT", "Salt"),
    ("PETROLEUM", "Petroleum"), ("OIL", "Oil"), ("CONDENSATE", "Condensate"),
    ("GAS", "Gas"), ("COAL", "Coal"), ("GEOTHERMAL", "Geothermal"),
    ("CO2", "CO2 storage"), ("WATER", "Water"), ("STRATIGRAPHY", "Stratigraphy"),
    ("SANDSTONE", "Sandstone"),
]
COMMODITY_NAMES = dict(COMMODITIES)
# catalog spellings -> one code
COMMODITY_ALIASES = {
    "REES": "REE", "BASE METAL": "BASE METALS", "FLUORITE": "F", "GAS+": "GAS",
    "CO2 SEQUESTATION": "CO2", "IRON": "FE", "ZIRCONIUM": "ZR", "PLATINUM GROUP ELEMENTS": "PGE",
}
# DASC spells names out ("NICKEL", "RARE EARTH ELEMENTS") -> the same codes
NAME_CODES = {name.upper().replace("-", " "): code for code, name in COMMODITIES}

# HyLogger's TSG group names (SWIR + TIR) -> what a geologist calls them
GROUP_NAMES = {
    "CHLORITE": "Chlorite", "WHITE-MICA": "White mica · sericite, muscovite",
    "AMPHIBOLE": "Amphibole · hornblende, actinolite",
    "CARBONATE": "Carbonate · calcite, dolomite, ankerite", "DARK-MICA": "Dark mica · biotite",
    "KAOLIN": "Kaolin clay", "EPIDOTE": "Epidote", "SMECTITE": "Smectite clay · montmorillonite",
    "SULPHATE": "Sulphate · gypsum, alunite, jarosite",
    "OTHER-ALOH": "Other Al-OH · prehnite, pyrophyllite, topaz", "OTHER-MGOH": "Other Mg-OH · talc",
    "SERPENTINE": "Serpentine", "TOURMALINE": "Tourmaline", "SILICA": "Silica · quartz",
    "PLAGIOCLASE": "Plagioclase feldspar", "K-FELDSPAR": "K-feldspar · orthoclase, microcline",
    "PYROXENE": "Pyroxene", "OLIVINE": "Olivine", "OXIDE": "Oxide", "PHOSPHATE": "Phosphate · apatite",
    "GARNET": "Garnet",
}

# A group counts as "in" a hole once it is at least this share of one metre.
# ponytail: one fixed cut-off - lower it if real-but-thin minerals go missing.
PRESENT_PCT = 10

LINK_LABELS = {
    "drill_report": "Drill Report", "summary_report": "Summary Report",
    "summary_histogram": "Summary Histogram", "tray_images": "Tray Images",
    "summary_mineral_logs": "Summary Mineral Logs",
}

# The vocab terms a decision hangs on, in reading order, each with why it
# matters. Keyed by the workbook's Preferred Label.
KEY_TERMS = {
    "SWIR": "Where the strip-log mineral comes from. Sees hydrous minerals - clays, micas, chlorite, "
            "carbonates, amphiboles - but not quartz, feldspar or garnet. A SWIR label is never the whole rock: "
            "GSWA's example is 100% white mica in SWIR for a rock that is 5% white mica and 95% quartz.",
    "TIR": "Sees almost all minerals, silicates included, so it is the better whole-rock picture. The same rock "
           "can read 100% quartz in TIR and 100% chlorite in SWIR; there is no agreed way to merge the two yet, "
           "so this site shows both side by side.",
    "Grp": "The mineral group (e.g. WHITE-MICA) - what the strip log colours by. On Level 1 data GSWA rates "
           "group labels as more accurate than individual mineral names.",
    "Min": "The specific mineral (e.g. Chlorite-Fe vs Chlorite-Mg). Most useful on Level 2 holes; even a wrong "
           "name can still show a real pattern down the hole.",
    "Wt": "The spectral weight of a mineral in the unmixing result. A Wt1 of 1 only means that one mineral alone "
          "models the spectrum - it is not a confidence score (weights can approach 8). Error is the confidence.",
    "Error": "How well the modelled spectrum fits the measured one - low error, more confidence. GSWA treats 1000 "
             "or less as viable; this site's confidence check is stricter (400).",
    "Signal to Noise Ratio": "Signal strength. GSWA treats 60 or more as viable; this site calls under 200 weak. "
                             "Dark or wet core reads noisy - trust its call less.",
    "Invalid": "Dark, noisy, featureless or badly fitted readings. A run of them is a gap in the data, not proof "
               "a mineral is absent.",
    "Aspectral": "No diagnostic features in SWIR. It can mean no hydrous minerals (e.g. no white mica) - or fine "
                 "sulphides, magnetite, carbon or very dark core. It is 'no answer', not 'nothing there'.",
    "Processing level": "How far a geologist has checked the interpretation - each hole's level is on its card. "
                        "Treat Level 1 mineral labels with caution.",
    "Level 1": "Automatic ('System', s-prefix) mineral calls only - mostly accurate, and even a misnamed mineral's "
               "distribution is informative. Check before relying on a single label.",
    "Level 2": "A geologist refined the minerals the unmixing may use ('User', u-prefix) - more accurate labels. "
               "This site reads User results wherever GSWA has released them.",
    "Level 3": "Geologist-refined within depth domains ('Domain', d-prefix) - GSWA produces it rarely.",
    "TSA": "The unmixing routine behind every SWIR mineral call: a best fit of 1-3 library minerals, "
           "an estimate, not a lab assay.",
    "jCLST": "The TIR unmixing routine (guided by the SWIR result) behind the TIR shares.",
    "sTSAV": "The visible/near-infrared version of TSA. GSWA almost never uses it (a limited mineral library), "
             "so this site doesn't either.",
    "Mask": "GSWA's Final Mask marks clean core; rows outside it are non-core, cracks or core edges. Most holes "
            "here were downloaded without it, so the site relies on TSG's invalid and aspectral classes instead.",
    "Summary histogram": "A whole hole's mineral abundances in one plot - the fastest screen of a hole "
                         "(the 'Summary Histogram' link on each hole).",
    "2200nm wavelength": "White-mica chemistry. Shifts down a hole or between holes are used to map "
                         "alteration zoning around hydrothermal ore systems.",
    "2250nm wavelength": "Chlorite chemistry (Fe vs Mg) - one 'CHLORITE' label can hide a real chemical change.",
    "11300nm height": "Relative carbonate abundance from TIR. Carbonate alteration is a common feature "
                      "of WA's Yilgarn gold systems.",
    "OTHER-ALOH": "A catch-all group (prehnite, pyrophyllite, topaz...) - read the specific mineral before "
                  "interpreting it.",
}

INDEX_KEY = "mineral_index"


def commodity_codes(text):
    """'Au, Cu' / 'ZN (VMS)' / 'NI-CO' / 'GOLD; NICKEL' -> ['AU', 'CU'] / ['ZN'] / ['NI', 'CO'] /
    ['AU', 'NI'], known codes only."""
    codes = []
    for token in re.split(r"[,;]", str(text or "").upper()):
        token = re.sub(r"\(.*?\)", "", token).strip()
        token = COMMODITY_ALIASES.get(token, token)
        token = NAME_CODES.get(token.replace("-", " "), token)
        for code in token.split("-") if token == "NI-CO" else [token]:
            if code in COMMODITY_NAMES and code not in codes:
                codes.append(code)
    return codes


def mineral_index():
    """Every logged hole's minerals, summed over its metres:

        {hole_id: {"metres": n,
                   "groups": {group: {"swir": sum %, "tir": sum %,
                                      "swir_metres": n >= PRESENT_PCT, "tir_metres": ...}},
                   "species": {species: metres where it was the dominant mineral}}},
        {species: its group}

    Rebuilt from all 117k measurements (~1-2 s), then cached until the
    measurements change - the same count + max-id key views.mineral_logs uses,
    since load_data replaces every row.
    """
    version = Measurement.objects.aggregate(count=Count("id"), last=Max("id"))
    key = f"{INDEX_KEY}:{version['count']}:{version['last']}"
    cached = cache.get(key)
    if cached:
        return cached
    holes, species_group = {}, {}
    rows = Measurement.objects.exclude(mix={}).values_list("hole_id", "mix", "mineral_1", "mineral_1_species")
    for hole_id, mix, group_1, species in rows.iterator(chunk_size=5000):
        hole = holes.setdefault(hole_id, {"metres": 0, "groups": {}, "species": {}})
        hole["metres"] += 1
        for kind, shares in mix.items():
            for group, share in shares.items():
                g = hole["groups"].setdefault(group, {"swir": 0, "tir": 0, "swir_metres": 0, "tir_metres": 0})
                g[kind] += share
                if share >= PRESENT_PCT:
                    g[f"{kind}_metres"] += 1
        if species:
            hole["species"][species] = hole["species"].get(species, 0) + 1
            species_group.setdefault(species, group_1)
    cache.set(key, (holes, species_group), timeout=None)
    return holes, species_group


def contains(hole, group):
    g = hole["groups"].get(group)
    return bool(g and (g["swir_metres"] or g["tir_metres"]))


def mineral_list():
    """The left-hand list: commodities most valuable first, detected groups
    rarest first, each group's specific minerals under it (rarest first)."""
    holes, species_group = mineral_index()
    catalogs = Hole.objects.exclude(catalog={}).values_list("catalog", flat=True)
    commodity_holes = Counter(code for c in catalogs for code in c.get("commodity", []))
    group_holes = Counter(g for h in holes.values() for g in h["groups"] if contains(h, g))
    species_holes = Counter(s for h in holes.values() for s in h["species"])

    groups = []
    for group, count in sorted(group_holes.items(), key=lambda item: (item[1], item[0])):
        species = [{"name": s, "holes": species_holes[s]} for s, g in species_group.items() if g == group]
        groups.append({
            "code": group, "name": GROUP_NAMES.get(group, group.title()), "holes": count,
            "species": sorted(species, key=lambda s: (s["holes"], s["name"])),
        })
    return {
        "commodities": [{"code": code, "name": name, "holes": commodity_holes[code]}
                        for code, name in COMMODITIES if commodity_holes[code]],
        "groups": groups,
        "present_pct": PRESENT_PCT,
        "logged_holes": len(holes),
        "catalog_holes": len(catalogs),
    }


def holes_matching(commodity=None, group=None, species=None):
    """hole_ids drilled for `commodity` / holding `group` / with `species` dominant somewhere."""
    if commodity:
        return set(Hole.objects.filter(catalog__commodity__contains=[commodity]).values_list("hole_id", flat=True))
    holes, _ = mineral_index()
    if group:
        return {hole_id for hole_id, h in holes.items() if contains(h, group)}
    return {hole_id for hole_id, h in holes.items() if species in h["species"]}


def richness(group=None, species=None, commodity=None):
    """hole_id -> how much of the chosen mineral each hole holds, for shading:

        group      its average share of the hole's logged metres, in %
                   (the larger of SWIR and TIR - the same number as the hole card)
        species    % of the hole's logged metres where it is the dominant mineral
        commodity  its best 5 m average grade in the lab assays, in ppm (= g/t);
                   holes without assays for it are left out (assays.py)
    """
    if commodity:
        elements = assays.COMMODITY_ELEMENTS.get(commodity)
        return {h: round(g[0], 4) for h, g in assays.hole_grades(elements).items()} if elements else {}
    holes, _ = mineral_index()
    values = {}
    for hole_id, h in holes.items():
        if group and contains(h, group):
            g = h["groups"][group]
            values[hole_id] = round(max(g["swir"], g["tir"]) / h["metres"], 1)
        elif species and species in h["species"]:
            values[hole_id] = round(100 * h["species"][species] / h["metres"], 1)
    return values


def hole_minerals(hole):
    """One hole's card: catalog facts, the five links, every mineral in it."""
    holes, species_group = mineral_index()
    h = holes.get(hole.hole_id, {"metres": 0, "groups": {}, "species": {}})
    metres = h["metres"] or 1
    groups = [{
        "code": group, "name": GROUP_NAMES.get(group, group.title()),
        # None = that sensor never saw it; 0.0 = seen, but under 0.05% on average
        "swir_pct": round(g["swir"] / metres, 1) if g["swir"] else None,
        "tir_pct": round(g["tir"] / metres, 1) if g["tir"] else None,
        "swir_metres": g["swir_metres"], "tir_metres": g["tir_metres"],
    } for group, g in h["groups"].items()]
    catalog = hole.catalog or {}
    return {
        "hole_id": hole.hole_id,
        "in_catalog": bool(catalog),
        "commodities": [{"code": c, "name": COMMODITY_NAMES[c]} for c in catalog.get("commodity", [])],
        "project": catalog.get("project"),
        "process_level": catalog.get("process_level"),
        "sample_type": catalog.get("type"),
        "location": catalog.get("location"),
        "links": [{"key": key, "label": label, "url": catalog.get("links", {}).get(key)}
                  for key, label in LINK_LABELS.items()],
        "logged_metres": h["metres"],
        "present_pct": PRESENT_PCT,
        "groups": sorted(groups, key=lambda g: -max(g["swir_pct"] or 0, g["tir_pct"] or 0)),
        "species": sorted(({"name": s, "group": species_group.get(s, ""), "metres": n}
                           for s, n in h["species"].items()), key=lambda s: -s["metres"]),
    }


def vocab():
    """Every vocab term; the KEY_TERMS ones first, in that order, with why they matter."""
    order = list(KEY_TERMS)
    terms = [{
        "slug": t.slug, "label": t.label, "alt_labels": t.alt_labels, "definition": t.definition,
        "broader": t.broader, "decision": KEY_TERMS.get(t.label),
    } for t in VocabTerm.objects.all()]
    if not terms:  # GSWA's vocabulary workbook isn't loaded (it isn't public): the FAQ notes alone
        terms = [{"slug": label.lower().replace(" ", "-"), "label": label, "alt_labels": "", "definition": "",
                  "broader": "", "decision": note} for label, note in KEY_TERMS.items()]
    key = sorted((t for t in terms if t["decision"]), key=lambda t: order.index(t["label"]))
    return {"key": key, "all": terms}
