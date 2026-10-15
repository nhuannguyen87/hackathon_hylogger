"""
The API. Every endpoint is a plain function - read it top to bottom.

    GET /api/holes/                        list holes (for the map)
    GET /api/holes/<id>/                   one hole's details
    GET /api/holes/<id>/measurements/      the depth log
    GET /api/holes/<id>/trays/             real core-tray photos + per-tray minerals (few holes)
    GET /api/holes/<id>/anomalies/         only the flagged intervals
    GET /api/holes/<id>/trace/             3D line points for deck.gl
    GET /api/holes/<id>/nearby/?km=25      other holes within N km (PostGIS)
    GET /api/holes/<id>/spectral-sample/   real VSWIR/TIR spectrum: instant for 5 holes
                                            (database5553/) + 15 holes (data5553/), live
                                            from NVCL for every other one
    GET /api/holes/<id>/core-strip/        continuous core-photo + TSG strip (core_strip.py output)
    GET /api/mineral-logs/                 every hole's mineral log at once, merged into runs (map)
    GET /api/minerals/                     Minerals tab list: commodities + detected minerals
    GET /api/minerals/richness/?group=X    how much of X each hole holds (map shading): % for a
                                           detected mineral, best 5 m assay ppm for a commodity
    GET /api/holes/<id>/assays/            the hole's lab assays + each element's best 5 m
    GET /api/holes/<id>/export.csv         per-metre log + assays as CSV, for logging software
    GET /api/qgis/holes.geojson            collars as QGIS points (takes /api/holes/'s filters)
    GET /api/qgis/intervals.geojson        logged metres as 3D lines down each hole (?holes=)
    GET /api/qgis/assays.geojson           assay intervals as 3D lines (?element=Au&holes=)
    GET /api/holes/<id>/minerals/          one hole's catalog facts, links, every mineral in it
    GET /api/vocab/                        GSWA HyLogger vocabulary, decision-critical terms first
    GET /api/distance/?a=H001&b=H002       distance between two holes (PostGIS)
    GET /api/stats/                        counts for the header
"""

import bisect
import csv
import json
import logging
import math
import sys
import threading
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.db.models import Count, Max, Min, Q
from django.db.models.functions import Greatest
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.text import slugify
from rest_framework.decorators import api_view
from rest_framework.exceptions import APIException
from rest_framework.response import Response

from . import assays, geology, minerals
from .etl4_bridge import fetch_spectral_sample as fetch_etl4_spectral_sample
from .geo import position, trace_points
from .nvcl_bridge import fetch_spectral_sample_cached, get_reader, own_datasets
from .tsg_bridge import fetch_spectral_sample as fetch_tsg_spectral_sample
from .models import CoreTray, Hole, Measurement
from .serializers import (
    CoreTraySerializer,
    HoleDetailSerializer,
    HoleListSerializer,
    MeasurementSerializer,
    MeasurementWithFeaturesSerializer,
)

# core_strip.py and nvcl_datasets.py live at the project root, not inside
# backend/ - same sys.path bootstrap nvcl_bridge.py already uses to reach
# root-level scripts.
sys.path.insert(0, str(settings.PROJECT_ROOT))
from core_strip import build_master_hole_strip  # noqa: E402
from nvcl_datasets import SAME_HOLE_KM, distance_km  # noqa: E402

logger = logging.getLogger(__name__)


class BadParameter(APIException):
    """A query parameter we can't use: 422, the same answer the FastAPI
    backend (github.com/nhuannguyen87/hylogger) gives - never a 500."""

    status_code = 422
    default_detail = "Invalid query parameter."


def number(request, name, default, low, high, cast=float):
    """?name= as a number in [low, high], or `default` when it's absent.
    Anything else - text, NaN, out of range - is a BadParameter, so a typo
    in a URL can't crash a view or (step_m=0) loop forever."""
    raw = request.GET.get(name, "").strip()
    if not raw:
        return default
    try:
        value = cast(raw)
    except ValueError:
        raise BadParameter(f"{name} must be a number") from None
    if not (math.isfinite(value) and low <= value <= high):
        raise BadParameter(f"{name} must be between {low} and {high}")
    return value

# Core-photo strips built on first request, in a background thread (a hole's
# ~90 NVCL tray photos take about a minute). hole_id -> None while building,
# else why it failed - kept until the server restarts, so a hole NVCL has no
# photos for isn't retried on every click.
_strip_builds = {}
_strip_lock = threading.Lock()
_strip_slots = threading.BoundedSemaphore(2)  # each build already runs 8 NVCL downloads


def holes_with_depth():
    """
    Every hole, plus how deep it goes as far as we know:

        logged_from_m, logged_to_m   top and bottom of its measurements
        drawn_length_m               how far down to draw it

    borehole_length_m is the GSWA catalog's "Total (m)" - metres of core
    SCANNED (Depth to - Depth from), not the hole's depth. Logging often
    starts well below the collar (05KCD001: 142 m scanned, logged
    59.5-201.5 m), so a hole is drawn to that or its deepest logged metre,
    whichever is further down.

    The hole serializers read these, so fetch holes through here for them.
    """
    return Hole.objects.annotate(
        logged_from_m=Min("measurements__depth_from_m"),
        logged_to_m=Max("measurements__depth_to_m"),
    ).annotate(
        # Postgres' GREATEST skips NULLs, so a hole with no measurements is
        # still drawn to borehole_length_m (and vice versa)
        drawn_length_m=Greatest("borehole_length_m", "logged_to_m"),
    ).order_by("hole_id")  # Django drops Meta.ordering from GROUP BY queries


@api_view(["GET"])
def hole_list(request):
    """
    Optional query parameters:
        ?search=bindi     match on hole id or name
        ?limit=200        cap the number returned (default 1000)
        ?anomalies_only=1 only holes that have at least one flagged interval
        ?commodity=AU     only holes drilled for it (GSWA catalog)
        ?group=CHLORITE   only holes where HyLogger detected it (see minerals.py)
        ?species=Chlorite-Fe  only holes where it was the dominant mineral somewhere
        ?with_photos=1    only holes with their own core-photo strip on disk (3D tab's list)
    """
    limit = number(request, "limit", 1000, 1, 5000, cast=int)
    return Response(HoleListSerializer(filtered_holes(request)[:limit], many=True).data)


def filtered_holes(request):
    """holes_with_depth() narrowed by hole_list's query parameters - shared
    with the QGIS layer, so the map and QGIS always pick the same holes."""
    holes = holes_with_depth()

    search = request.GET.get("search", "").strip()
    if search:
        holes = holes.filter(Q(hole_id__icontains=search) | Q(hole_name__icontains=search))

    if request.GET.get("anomalies_only") == "1":
        # a subquery, not a join on measurements - that would multiply the
        # rows holes_with_depth() aggregates over
        flagged = Measurement.objects.filter(is_anomaly=True).values("hole_id")
        holes = holes.filter(hole_id__in=flagged)

    if request.GET.get("with_photos") == "1":
        holes = holes.filter(hole_id__in=holes_with_photos())

    wanted = {key: request.GET.get(key) for key in ("commodity", "group", "species")}
    if any(wanted.values()):
        holes = holes.filter(hole_id__in=minerals.holes_matching(**wanted))
    return holes


@api_view(["GET"])
def hole_detail(request, hole_id):
    hole = get_object_or_404(
        holes_with_depth().annotate(
            measurement_count=Count("measurements", distinct=True),
            anomaly_count=Count("measurements", filter=Q(measurements__is_anomaly=True), distinct=True),
        ),
        pk=hole_id,
    )
    return Response(HoleDetailSerializer(hole).data)


@api_view(["GET"])
def hole_measurements(request, hole_id):
    """?with_features=1 also returns the raw band values."""
    get_object_or_404(Hole, pk=hole_id)
    rows = Measurement.objects.filter(hole_id=hole_id).order_by("depth_from_m")

    serializer_class = (
        MeasurementWithFeaturesSerializer
        if request.GET.get("with_features") == "1"
        else MeasurementSerializer
    )
    return Response(serializer_class(rows, many=True).data)


@api_view(["GET"])
def mineral_list(request):
    return Response(minerals.mineral_list())


@api_view(["GET"])
def mineral_richness(request):
    """?group=CHLORITE / ?species=Chlorite-Fe -> {hole_id: %}; ?commodity=AU ->
    {hole_id: best 5 m ppm}. See minerals.richness."""
    wanted = {key: request.GET.get(key) for key in ("group", "species", "commodity")}
    if sum(bool(v) for v in wanted.values()) != 1:
        raise BadParameter("Pass exactly one of ?group=, ?species= or ?commodity=")
    return Response(minerals.richness(**wanted))


@api_view(["GET"])
def hole_assays(request, hole_id):
    return Response(assays.hole_assays(get_object_or_404(Hole, pk=hole_id)))


@api_view(["GET"])
def hole_geology(request, hole_id):
    return Response(geology.hole_geology(get_object_or_404(Hole, pk=hole_id)))


@api_view(["GET"])
def hole_minerals(request, hole_id):
    return Response(minerals.hole_minerals(get_object_or_404(Hole, pk=hole_id)))


@api_view(["GET"])
def vocab(request):
    return Response(minerals.vocab())


# ------------------------------------------------------------------ QGIS
# Plain GeoJSON (EPSG:4326, z in metres) that QGIS opens straight from the URL:
# Layer > Add Layer > Add Vector Layer > Protocol: HTTP(S). Each feature
# carries a `colour` field - the site's own palette - for data-defined styling.

PALETTE = json.loads((settings.PROJECT_ROOT / "frontend" / "mineral-colours.json").read_text())


def geojson(features):
    response = JsonResponse({"type": "FeatureCollection", "features": features}, json_dumps_params={"separators": (",", ":")})
    response["Access-Control-Allow-Origin"] = "*"  # QGIS and other GIS tools, not just the site
    return response


def hole_ids(request):
    """?holes=ID,ID -> those ids (404s are QGIS-unfriendly, so unknown ones are skipped)."""
    raw = request.GET.get("holes", "").strip()
    return [h.strip() for h in raw.split(",") if h.strip()] if raw else None


def qgis_holes(request):
    """Every hole (hole_list's filters apply) as a point with what a GIS user
    filters and styles on: dominant SWIR mineral, processing level,
    commodity, best 5 m gold, unusual metres, GSWA document links."""
    index, _ = minerals.mineral_index()
    gold = assays.hole_grades(["Au"])
    unusual = dict(Measurement.objects.filter(is_anomaly=True).values_list("hole_id").annotate(n=Count("id")))
    features = []
    for hole in filtered_holes(request):
        groups = index.get(hole.hole_id, {}).get("groups", {})
        dominant = max(groups, key=lambda g: groups[g]["swir"], default=None) if groups else None
        catalog = hole.catalog or {}
        links = catalog.get("links", {})
        features.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": position(hole, 0)}, "properties": {
            "hole_id": hole.hole_id, "length_m": hole.drawn_length_m, "logged": hole.hole_id in index,
            "dominant_swir_mineral": dominant, "colour": PALETTE["groups"].get(dominant, PALETTE["unknown"]),
            "processing_level": catalog.get("process_level"), "commodity": ", ".join(catalog.get("commodity", [])),
            "au_best5m_ppm": round(gold[hole.hole_id][0], 4) if hole.hole_id in gold else None,
            "unusual_metres": unusual.get(hole.hole_id, 0), "confidential": hole.confidential,
            "drill_report": links.get("drill_report"), "summary_histogram": links.get("summary_histogram"),
            "tray_images": links.get("tray_images"),
            "position_source": catalog.get("position", {}).get("source", "NVCL catalog"),
            "position_note": catalog.get("position", {}).get("note"),
        }})
    return geojson(features)


def qgis_intervals(request):
    """Each logged metre as a 3D line down its hole (?holes=ID,ID; default:
    every logged hole, ~115k lines). Uncertain metres keep the site's grey."""
    rows = Measurement.objects.order_by("hole_id", "depth_from_m")
    if (wanted := hole_ids(request)) is not None:
        rows = rows.filter(hole_id__in=wanted)
    holes = Hole.objects.in_bulk(list(rows.values_list("hole_id", flat=True).distinct()))
    features = []
    for m in rows.only("hole_id", "depth_from_m", "depth_to_m", "mineral_1", "mineral_1_species",
                       "confidence", "quality_flag", "is_anomaly").iterator(chunk_size=5000):
        hole = holes[m.hole_id]
        uncertain = m.quality_flag == "missing" or m.confidence < 0.5  # frontend CONFIDENCE_THRESHOLD
        features.append({"type": "Feature", "geometry": {"type": "LineString", "coordinates": [
            position(hole, m.depth_from_m), position(hole, m.depth_to_m)]}, "properties": {
            "hole_id": m.hole_id, "from_m": m.depth_from_m, "to_m": m.depth_to_m,
            "mineral_group": m.mineral_1, "mineral": m.mineral_1_species, "confidence": m.confidence,
            "uncertain": uncertain, "unusual": m.is_anomaly,
            "colour": PALETTE["uncertain"] if uncertain else PALETTE["groups"].get(m.mineral_1, PALETTE["unknown"]),
        }})
    return geojson(features)


def qgis_assays(request):
    """Assay intervals of one element (?element=Au, the default) as 3D lines,
    ppm per interval - below detection and suspect units flagged, never mixed in."""
    element = request.GET.get("element", "Au")
    if element not in assays.ELEMENTS:  # a plain Django view: BadParameter would be a 500 here
        return JsonResponse({"detail": f"element must be one of {', '.join(assays.ELEMENTS)}"}, status=422)
    rows = assays.measured([element]).order_by("hole_id", "depth_from_m")
    if (wanted := hole_ids(request)) is not None:
        rows = rows.filter(hole_id__in=wanted)
    holes = Hole.objects.in_bulk(list(rows.values_list("hole_id", flat=True).distinct()))
    features = [{"type": "Feature", "geometry": {"type": "LineString", "coordinates": [
        position(holes[a.hole_id], a.depth_from_m), position(holes[a.hole_id], a.depth_to_m)]}, "properties": {
        "hole_id": a.hole_id, "from_m": a.depth_from_m, "to_m": a.depth_to_m, "element": element,
        "ppm": a.values.get(element), "below_detection": element in a.below_detection,
        "suspect_ppm": a.suspect.get(element),
    }} for a in rows.iterator(chunk_size=5000)]
    return geojson(features)


def hole_export(request, hole_id):
    """The hole's per-metre mineral log with its logged rock and assays, one row per metre.
    Each element is the length-weighted average of the assays overlapping
    that metre: "<DL" when all were below detection, blank when none was
    measured; suspect values are left out (assays.py)."""
    hole = get_object_or_404(Hole, pk=hole_id)
    metres = list(Measurement.objects.filter(hole=hole).order_by("depth_from_m"))
    lab = list(hole.assays.order_by("depth_from_m"))
    elements = [e for e in assays.ELEMENTS if any(e in a.values or e in a.below_detection for a in lab)]
    rocks = list(hole.geology.order_by("depth_from_m"))

    def rock_at(depth):  # ponytail: linear scan, a hole has at most a few thousand intervals
        hit = next((g for g in rocks if g.depth_from_m <= depth < g.depth_to_m), None)
        return "" if hit is None else hit.rock or hit.name or f"code {hit.code}"
    mix = lambda shares: "; ".join(f"{g} {p}" for g, p in sorted((shares or {}).items(), key=lambda kv: -kv[1]))  # noqa: E731

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{slugify(hole_id) or "hole"}_hylogger.csv"'
    writer = csv.writer(response)
    writer.writerow([f"# {hole_id}. Minerals: GSWA HyLogger data via NVCL (CC BY 4.0). Assays: company results "
                     "reported to WAMEX, compiled in GSWA's DASC HyLogger Drillhole Package (CC BY 4.0), no GSWA QC. "
                     "Logged rock: company logging (WAMEX), GSWA's name where it gave one."])
    writer.writerow(["hole_id", "depth_from_m", "depth_to_m", "mineral_group_swir", "mineral", "dominance_wt",
                     "confidence", "quality", "why", "swir_mix_pct", "tir_mix_pct", "unusual", "anomaly_score",
                     "logged_rock", *[f"{e}_ppm" for e in elements]])
    start = 0
    for m in metres:
        while start < len(lab) and lab[start].depth_to_m <= m.depth_from_m:
            start += 1
        overlap = []
        for a in lab[start:]:
            if a.depth_from_m >= m.depth_to_m:
                break
            overlap.append((min(a.depth_to_m, m.depth_to_m) - max(a.depth_from_m, m.depth_from_m), a))
        grades = []
        for element in elements:
            parts = [(w, assays.interval_value(a, [element])) for w, a in overlap]
            parts = [(w, v) for w, v in parts if v is not None and w > 0]
            if not parts:
                grades.append("")
            elif all(v == 0 for _, v in parts):
                grades.append("<DL")
            else:
                grades.append(round(sum(w * v for w, v in parts) / sum(w for w, _ in parts), 4))
        writer.writerow([hole_id, m.depth_from_m, m.depth_to_m, m.mineral_1, m.mineral_1_species, m.mineral_1_pct,
                         m.confidence, m.quality_flag, m.why, mix(m.mix.get("swir")), mix(m.mix.get("tir")),
                         "yes" if m.is_anomaly else "", m.anomaly_score,
                         rock_at((m.depth_from_m + m.depth_to_m) / 2), *grades])
    return response


@api_view(["GET"])
def hole_trays(request, hole_id):
    """Real core-tray photos + per-tray mineral calls, where we have them.

    Empty for most holes - only loaded so far for holes whose HyLogger
    package included a processed mineral-by-tray table (see
    management/commands/load_core_trays.py). An empty list here is
    normal, not an error; the frontend treats it that way.
    """
    get_object_or_404(Hole, pk=hole_id)
    rows = CoreTray.objects.filter(hole_id=hole_id).order_by("depth_from_m")
    return Response(CoreTraySerializer(rows, many=True).data)


@api_view(["GET"])
def hole_anomalies(request, hole_id):
    get_object_or_404(Hole, pk=hole_id)  # an unknown hole is a 404, not "no anomalies"
    rows = (
        Measurement.objects.filter(hole_id=hole_id, is_anomaly=True)
        .order_by("-anomaly_score")
    )
    return Response(MeasurementSerializer(rows, many=True).data)


@api_view(["GET"])
def hole_trace(request, hole_id):
    """
    Points down the hole for the 3D view, in metres from the collar.
    Each point also carries the mineral and anomaly score at that depth, so
    deck.gl can colour the line without a second request.

    Runs down to drawn_length_m, not borehole_length_m - see holes_with_depth().
    """
    hole = get_object_or_404(holes_with_depth(), pk=hole_id)
    step = number(request, "step_m", 5.0, 0.5, 100)

    points = trace_points(
        hole.inclination_deg, hole.azimuth_deg, hole.drawn_length_m or 0, step_m=step
    )

    # attach the measurement that covers each point's depth - a binary search
    # on the sorted interval tops, not a scan of every interval per point
    logs = list(Measurement.objects.filter(hole_id=hole_id).order_by("depth_from_m"))
    tops = [m.depth_from_m for m in logs]
    for point in points:
        i = bisect.bisect_right(tops, point["depth_m"]) - 1
        match = logs[i] if i >= 0 and point["depth_m"] < logs[i].depth_to_m else None
        point["mineral"] = match.mineral_1 if match else ""
        point["confidence"] = match.confidence if match else 0.0
        point["anomaly_score"] = (match.anomaly_score if match else None) or 0.0
        point["is_anomaly"] = bool(match.is_anomaly) if match else False

    return Response({
        "hole_id": hole.hole_id,
        "hole_name": hole.hole_name,
        "latitude": hole.latitude,
        "longitude": hole.longitude,
        "elevation_m": hole.elevation_m,
        "points": points,
    })


def merge_mineral_runs(min_confidence):
    """
    Every hole's measurements as runs of the same call, shallow to deep:
    consecutive, touching intervals with the same mineral_1 (or both
    uncertain) become one [from_m, to_m, group] - 49k one-metre intervals
    come out as ~11k runs. Uncertain means what StripLog.jsx hatches:
    quality_flag "missing" or confidence under min_confidence.
    """
    groups, index, holes = [], {}, {}
    rows = Measurement.objects.order_by("hole_id", "depth_from_m").values_list(
        "hole_id", "depth_from_m", "depth_to_m", "mineral_1", "confidence", "quality_flag"
    )
    for hole_id, top, bottom, mineral, confidence, quality in rows.iterator(chunk_size=10000):
        if quality == "missing" or (confidence or 0.0) < min_confidence:
            code = None
        else:
            if mineral not in index:
                index[mineral] = len(groups)
                groups.append(mineral)
            code = index[mineral]
        runs = holes.setdefault(hole_id, [])
        if runs and runs[-1][2] == code and abs(runs[-1][1] - top) < 1e-6:
            runs[-1][1] = round(bottom, 3)
        else:
            runs.append([round(top, 3), round(bottom, 3), code])
    return {"groups": groups, "holes": holes}


@api_view(["GET"])
def mineral_logs(request):
    """
    Every hole's mineral log in one response, for the map to colour each 3D
    core on first load instead of only the hole you click (whose
    /measurements/ the detail panel fetches).

        ?min_confidence=0.5   below this an interval counts as uncertain -
                              pass the frontend's CONFIDENCE_THRESHOLD, so the
                              map greys out the same intervals StripLog hatches

        {"groups": ["CHLORITE", ...],
         "holes": {"05GJD001": [[150.0, 163.0, 0], [163.0, 164.0, null], ...]}}

    A run is [from_m, to_m, index into "groups"], or null when uncertain.
    Holes with no measurements aren't listed. Cached until the measurements
    change - load_data replaces them, which moves their count and max id.
    """
    min_confidence = number(request, "min_confidence", 0.5, 0, 1)

    version = Measurement.objects.aggregate(count=Count("id"), last=Max("id"))
    key = f"mineral-logs:{version['count']}:{version['last']}:{min_confidence}"
    payload = cache.get(key)
    if payload is None:
        payload = merge_mineral_runs(min_confidence)
        cache.set(key, payload, timeout=None)
    return Response(payload)


@api_view(["GET"])
def distance(request):
    """
    Straight-line distance across the earth's surface between two collars.
    PostGIS does the maths - don't reimplement this in JavaScript.
    """
    a_id = request.GET.get("a")
    b_id = request.GET.get("b")
    if not a_id or not b_id:
        raise BadParameter("Pass ?a=HOLE_ID&b=HOLE_ID")

    a = get_object_or_404(holes_with_depth(), pk=a_id)
    b = get_object_or_404(holes_with_depth(), pk=b_id)

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT ST_DistanceSphere(
                ST_SetSRID(ST_MakePoint(%s, %s), 4326),
                ST_SetSRID(ST_MakePoint(%s, %s), 4326)
            )
            """,
            [a.longitude, a.latitude, b.longitude, b.latitude],
        )
        metres = cursor.fetchone()[0]

    return Response({
        "hole_a": HoleListSerializer(a).data,
        "hole_b": HoleListSerializer(b).data,
        "distance_m": round(metres, 1),
        "distance_km": round(metres / 1000, 3),
    })


@api_view(["GET"])
def hole_nearby(request, hole_id):
    """?km=25 - other holes within that radius, nearest first."""
    hole = get_object_or_404(Hole, pk=hole_id)
    radius_km = number(request, "km", 25.0, 0.1, 500)

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT hole_id, hole_name, latitude, longitude, borehole_length_m,
                   ST_DistanceSphere(
                       ST_SetSRID(ST_MakePoint(longitude, latitude), 4326),
                       ST_SetSRID(ST_MakePoint(%s, %s), 4326)
                   ) AS metres
            FROM holes
            WHERE hole_id <> %s
              -- ST_DWithin on geography is the bit that uses the spatial index
              AND ST_DWithin(
                      ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography,
                      ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                      %s
                  )
            ORDER BY metres
            LIMIT 50
            """,
            [hole.longitude, hole.latitude, hole_id,
             hole.longitude, hole.latitude, radius_km * 1000],
        )
        columns = [c[0] for c in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

    for row in rows:
        row["distance_km"] = round(row.pop("metres") / 1000, 3)

    return Response(rows)


@api_view(["GET"])
def hole_spectral_sample(request, hole_id):
    """
    Real VSWIR/TIR spectrum + mineral call nearest ?depth_m=, tried in order:
      1. the 5 holes restored from database5553/ (instant, etl4_bridge.py)
      2. the 15 holes with a raw TSG package in data5553/ (instant, a local
         file read - tsg_bridge.py)
      3. every other hole: a live NVCL lookup (a few seconds the first time,
         then cached - nvcl_bridge.py)
    404 only if none of the three has anything - a hole with no spectral log
    at all, or NVCL unreachable - which the frontend treats as a normal,
    expected state.
    """
    get_object_or_404(Hole, pk=hole_id)  # don't ask NVCL about holes we don't have
    depth_m = number(request, "depth_m", None, 0, 20000)

    sample = fetch_etl4_spectral_sample(hole_id, depth_m)
    if sample is None:
        sample = fetch_tsg_spectral_sample(hole_id, depth_m)
    if sample is None:
        sample = fetch_spectral_sample_cached(hole_id, depth_m)
    if sample is None:
        return Response({"detail": "No spectral data available for this hole."}, status=404)
    return Response(sample)


def holes_with_photos():
    """hole_ids whose core-photo strip is built and holds their own photos -
    the test hole_core_strip serves by. Cached per number of built strips,
    since a strip is only ever added (a first view builds it)."""
    root = Path(settings.DATA_DIR) / "media" / "core_strips"
    tables = {p.parent.name: p for p in root.glob("*/depth_pixel_table.json")}
    key = f"holes-with-photos:{len(tables)}"
    ready = cache.get(key)
    if ready is None:
        ready = {
            hole_id for hole_id, hole in Hole.objects.in_bulk(list(tables)).items()
            if photos_from_elsewhere(hole, json.loads(tables[hole_id].read_text(encoding="utf-8-sig"))) is None
        }
        cache.set(key, ready, timeout=None)
    return ready


def photos_from_elsewhere(hole, table):
    """
    Why a core-photo strip's photos aren't this hole's, or None if they are.

    One NVCL id can cover two different holes. "BH01" here is a 3.6 m
    Bunbury bore, but NVCL also files a Behemoth hole 1,250 km away under
    it (dataset "BH01_Behemoth"), and that hole's photos were once served
    as BH01's. So core_strip.py records the NVCL datasets its photos came
    from, and each must be this hole's: named after it, or with a TSG
    header collar within SAME_HOLE_KM of the holes table's collar.
    """
    sources = table.get("source_datasets")
    if not sources:
        return ("This core-photo strip doesn't record which NVCL datasets its photos came from, "
                "so it can't be matched to this hole - rebuild it with core_strip.py.")
    for source in sources:
        name = source.get("dataset_name")
        if name == hole.hole_id:
            continue
        collar = source.get("tsg_collar")
        km = distance_km(tuple(collar), (hole.latitude, hole.longitude)) if collar else None
        if km is None:
            return (f"These core photos are from NVCL dataset {name}, which isn't named {hole.hole_id} "
                    "and doesn't record its collar, so they can't be matched to this hole.")
        if km > SAME_HOLE_KM:
            return (f"These core photos are from NVCL dataset {name}, whose collar is {km:,.1f} km "
                    f"from {hole.hole_id}'s - a different hole, so they aren't shown here.")
    return None


@api_view(["GET"])
def hole_core_strip(request, hole_id):
    """
    Continuous core-photo strip, built by core_strip.py (repo root) from
    real GSWA/NVCL tray photos - see that file for how depth maps to pixels.

    Any hole works, not just pre-built ones: the first request starts a
    background build (build_core_strip - the hole's NVCL tray photos,
    streamed, ~1 min) and answers 202 {"status": "building"}; the frontend
    polls until the strip is on disk, then it's served from there on every
    later request. `core_strip.py --all` pre-builds the downloaded holes so
    they never wait. 404 for a hole that isn't in the holes table, one NVCL
    has no tray photos for, or one whose strip holds another hole's photos
    (photos_from_elsewhere) - the frontend treats all of those as a normal,
    expected state, same convention as spectral-sample above.
    """
    hole = get_object_or_404(Hole, pk=hole_id)
    strip_dir = Path(settings.DATA_DIR) / "media" / "core_strips" / hole_id
    table_path = strip_dir / "depth_pixel_table.json"
    if not table_path.is_file():
        with _strip_lock:
            if hole_id not in _strip_builds:
                _strip_builds[hole_id] = None
                threading.Thread(target=build_core_strip, args=(hole_id,), daemon=True).start()
            failed = _strip_builds[hole_id]
        if failed:
            return Response({"detail": failed}, status=404)
        return Response({"status": "building",
                         "detail": "Building this hole's core photo from its NVCL tray photos."}, status=202)

    with table_path.open(encoding="utf-8-sig") as handle:
        table = json.load(handle)

    elsewhere = photos_from_elsewhere(hole, table)
    if elsewhere:
        return Response({"detail": elsewhere}, status=404)

    base = f"{settings.MEDIA_URL}core_strips/{hole_id}/"
    sheets = [
        {
            "sheet_index": sheet["sheet_index"],
            "depth_from_m": sheet["depth_from_m"],
            "depth_to_m": sheet["depth_to_m"],
            "width_px": sheet["width_px"],
            "height_px": sheet["height_px"],
            "photo_url": base + sheet["file"],
            # null when NVCL has no TSA mineral log for this hole's photos
            "tsg_url": (base + tsg.name) if (tsg := strip_dir / f"tsg_sheet_{sheet['sheet_index']}.png").is_file() else None,
        }
        for sheet in table["sheets"]
    ]
    # Per-row breakpoints too (not just the per-sheet summary) - the 3D view
    # needs these to crop an exact depth-range slice out of a sheet image for
    # texturing a cylinder segment, the same depth<->pixel mapping
    # depth_lookup.py itself uses.
    rows = [
        {
            "sheet_index": row["sheet_index"],
            "depth_from_m": row["depth_from_m"],
            "depth_to_m": row["depth_to_m"],
            "y_from_px": row["y_from_px"],
            "y_to_px": row["y_to_px"],
        }
        for row in table["rows"]
    ]
    return Response({
        "hole_id": hole_id,
        "source_datasets": table["source_datasets"],
        "depth_min_m": table["depth_min_m"],
        "depth_max_m": table["depth_max_m"],
        "core_width_px": table["core_width_px"],
        "sheets": sheets,
        "rows": rows,
    })


def build_core_strip(hole_id):
    """Background thread for hole_core_strip: the hole's photo strip (and its
    mineral strip, where NVCL has a TSA log). A hole with no data/raw folder
    (catalog-only) gets its NVCL datasets looked up live."""
    try:
        with _strip_slots:
            datasets = None
            if not (Path(settings.DATA_DIR) / "raw" / hole_id / "datasets.json").is_file():
                found = own_datasets(get_reader(), hole_id)
                if found is None:
                    raise ValueError("NVCL has no datasets for this hole")
                datasets = found[1]
            build_master_hole_strip(hole_id, datasets=datasets, reader=get_reader())
        with _strip_lock:
            _strip_builds.pop(hole_id, None)
    except Exception as exc:  # noqa: BLE001 - any failure is "no photos", never a crash
        logger.warning("core strip for %s failed: %s", hole_id, exc)
        with _strip_lock:
            _strip_builds[hole_id] = f"No core photos available for this hole: {exc}"
    finally:
        connection.close()  # this thread's own DB connection (own_datasets reads Hole)


@api_view(["GET"])
def stats(request):
    return Response({
        "holes": Hole.objects.count(),
        "measurements": Measurement.objects.count(),
        "anomalies": Measurement.objects.filter(is_anomaly=True).count(),
        "low_confidence": Measurement.objects.filter(confidence__lt=0.5).count(),
    })
