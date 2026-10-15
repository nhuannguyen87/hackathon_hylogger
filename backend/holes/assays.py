"""
Lab assays (company chemistry from WAMEX reports, compiled in GSWA's DASC
interim package) - how a raw value becomes something the site can show.

Three rules, from the data itself and the package's disclaimer:

  below detection  companies code "less than the lab could detect" as a
                   negative number (-0.01, but also -5, -5000). Never shown as
                   a number; counted as 0 in averages.
  suspect units    a value above what rock can hold (one gold assay reads
                   421,300 ppm - 42% gold) is almost always a unit mix-up. The
                   disclaimer says to disregard such values, so they're kept
                   apart and left out of every average.
  best 5 m         a hole's grade for an element is its richest stretch of at
                   least 5 m, averaged by interval length - GSWA's FAQ frames
                   a gold ore/waste cut-off as 10 ppb over a 5 m average, and
                   one spike can't decide the whole hole.
"""

# element -> its column in WAMEX_AssayFlatData (all ppm; ppm = g/t)
ELEMENTS = {
    "Au": "Au_PPM", "Ag": "Ag_PPM", "Pt": "Pt_PPM", "Pd": "Pd_PPM",
    "Cu": "Cu_PPM", "Ni": "Ni_PPM", "Co": "Co_PPM", "Zn": "Zn_PPM", "Pb": "Pb_PPM",
    "Li": "Li_PPM", "U": "U_PPM", "Mo": "Mo_PPM", "W": "W_PPM", "Sn": "Sn_PPM",
    "Ta": "Ta_PPM", "Nb": "Nb_PPM", "V": "V_PPM", "Cr": "Cr_PPM", "Mn": "Mn_PPM",
    "Fe": "Fe_PPM", "Ce": "Ce_PPM", "Nd": "Nd_PPM", "Pr": "Pr_PPM", "Dy": "Dy_PPM",
    # pathfinders the FAQ names around ore (arsenic) and sulphides (sulphur)
    "As": "As_PPM", "S": "S_PPM",
}

# Highest believable value, ppm: precious metals catch the common
# ppb-reported-as-ppm errors; ores are capped at their purest mineral
# (hematite ~70% Fe, pyrolusite ~63% Mn, pyrite ~53% S, molybdenite ~60% Mo,
# spodumene ~3.7% Li); anything else above 50% is treated as a unit error.
# ponytail: one cap per element, not per deposit type.
CEILING_PPM = {"Au": 1000, "Pt": 1000, "Pd": 1000, "Ag": 20000, "Li": 40000, "U": 100000,
               "Fe": 700000, "Mn": 700000, "S": 540000, "Mo": 600000}
DEFAULT_CEILING_PPM = 500000

# what each catalog commodity is measured by (PGE: platinum + palladium together)
COMMODITY_ELEMENTS = {
    "AU": ["Au"], "AG": ["Ag"], "PT": ["Pt"], "PD": ["Pd"], "PGE": ["Pt", "Pd"],
    "CU": ["Cu"], "NI": ["Ni"], "CO": ["Co"], "ZN": ["Zn"], "PB": ["Pb"], "LI": ["Li"],
    "U": ["U"], "MO": ["Mo"], "W": ["W"], "SN": ["Sn"], "TA": ["Ta"], "NB": ["Nb"],
    "V": ["V"], "CR": ["Cr"], "MN": ["Mn"], "FE": ["Fe"], "CE": ["Ce"], "ND": ["Nd"],
    "PR": ["Pr"], "DY": ["Dy"],
}

# GSWA's FAQ gives one: gold, 10 ppb (0.01 ppm) over a 5 m average
CUTOFF_PPM = {"Au": 0.01}
WINDOW_M = 5.0


def classify(element, raw):
    """A raw table value -> ("value", ppm) | ("below_detection", None) |
    ("suspect", raw) | (None, None) when there's nothing usable."""
    if raw is None or raw != raw:  # missing or NaN
        return None, None
    if raw < 0:
        return "below_detection", None
    if raw > CEILING_PPM.get(element, DEFAULT_CEILING_PPM):
        return "suspect", raw
    return "value", raw


def interval_value(assay, elements):
    """ppm of `elements` summed for one Assay row; 0 when all were below
    detection, None when none was measured or one is suspect."""
    total, measured = 0.0, False
    for element in elements:
        if element in assay.suspect:
            return None
        if element in assay.values:
            total += assay.values[element]
            measured = True
        elif element in assay.below_detection:
            measured = True
    return total if measured else None


def best_window(intervals, width=WINDOW_M):
    """Highest length-weighted average over a run of intervals spanning at
    least `width` metres - or over all of them when the hole has less.

        intervals: [(from_m, to_m, ppm or None)], sorted by depth
        returns:   (average, from_m, to_m), or None if nothing was measured

    Unmeasured (None) intervals are skipped: a gap is not a zero.
    """
    rows = [(a, b, v) for a, b, v in intervals if v is not None and b > a]
    if not rows:
        return None
    best = None
    for i in range(len(rows)):
        length = weighted = 0.0
        for j in range(i, len(rows)):
            a, b, v = rows[j]
            length += b - a
            weighted += (b - a) * v
            if rows[j][1] - rows[i][0] >= width:
                break
        if rows[j][1] - rows[i][0] < width and i > 0:
            break  # the rest of the hole is shorter than one window; window 0 covered it
        average = weighted / length
        if best is None or average > best[0]:
            best = (average, rows[i][0], rows[j][1])
    return best


# ---------------------------------------------------------------- from the DB

from collections import defaultdict  # noqa: E402

from django.core.cache import cache  # noqa: E402
from django.db.models import Count, Max, Q  # noqa: E402

from .models import Assay  # noqa: E402

SOURCE = ("Company lab assays reported to WAMEX, as compiled in GSWA's DASC HyLogger Drillhole Package "
          "(interim release, CC BY 4.0). GSWA did no quality control on these values - check the "
          "original report when in doubt.")


def measured(elements):
    """Assay rows that say anything about any of `elements`."""
    query = Q()
    for element in elements:
        query |= Q(values__has_key=element) | Q(below_detection__contains=[element]) | Q(suspect__has_key=element)
    return Assay.objects.filter(query)


def hole_grades(elements):
    """{hole_id: (best 5 m average ppm, from_m, to_m)} for `elements` summed
    per interval. Cached until the assays change (load_interim replaces them)."""
    version = Assay.objects.aggregate(count=Count("id"), last=Max("id"))
    key = f"grades:{version['count']}:{version['last']}:{'+'.join(elements)}"
    grades = cache.get(key)
    if grades is None:
        by_hole = defaultdict(list)
        rows = measured(elements).order_by("hole_id", "depth_from_m").only(
            "hole_id", "depth_from_m", "depth_to_m", "values", "below_detection", "suspect")
        for row in rows.iterator(chunk_size=5000):
            by_hole[row.hole_id].append((row.depth_from_m, row.depth_to_m, interval_value(row, elements)))
        grades = {hole_id: best for hole_id, intervals in by_hole.items() if (best := best_window(intervals))}
        cache.set(key, grades, timeout=None)
    return grades


def hole_assays(hole):
    """One hole's intervals plus each element's best 5 m, for the assay track."""
    rows = list(hole.assays.order_by("depth_from_m"))
    present = set()
    for row in rows:
        present |= set(row.values) | set(row.below_detection) | set(row.suspect)
    elements = [e for e in ELEMENTS if e in present]  # precious metals first
    best = {}
    for element in elements:
        found = best_window([(r.depth_from_m, r.depth_to_m, interval_value(r, [element])) for r in rows])
        if found:
            best[element] = {"ppm": round(found[0], 4), "from_m": found[1], "to_m": found[2]}
    return {
        "elements": elements,
        "intervals": [{"from_m": r.depth_from_m, "to_m": r.depth_to_m, "values": r.values,
                       "below_detection": r.below_detection, "suspect": r.suspect} for r in rows],
        "best": best,
        "cutoff_ppm": CUTOFF_PPM,
        "window_m": WINDOW_M,
        "source": SOURCE,
    }
