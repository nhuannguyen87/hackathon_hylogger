"""
Turning a hole into a 3D line.

A hole has a collar (where it breaks surface), an inclination and an azimuth.
We assume those stay constant down the hole - the "tangent method". That is
good enough to draw, and it is what most holes look like anyway.

If you later get downhole survey stations (depth, inclination, azimuth at
several depths), replace `trace_points` with the minimum-curvature method.
The rest of the app won't notice - it only cares about the returned shape.
"""

import math


METRES_PER_DEGREE_LAT = 110540  # frontend/lib/desurvey.js uses the same


def position(hole, depth_m):
    """[lon, lat, z] of the point `depth_m` down the hole's straight collar
    dip/azimuth line - frontend/lib/desurvey.js's desurveyPoint, unexaggerated,
    so a QGIS layer lands exactly where the site draws the core. z is metres
    relative to sea level when the collar elevation is known, else to the collar."""
    inclination = math.radians(hole.inclination_deg if hole.inclination_deg is not None else -90.0)
    azimuth = math.radians(hole.azimuth_deg or 0.0)
    horizontal = depth_m * math.cos(inclination)
    per_degree_lon = METRES_PER_DEGREE_LAT * math.cos(math.radians(hole.latitude))
    return [
        round(hole.longitude + horizontal * math.sin(azimuth) / per_degree_lon, 7),
        round(hole.latitude + horizontal * math.cos(azimuth) / METRES_PER_DEGREE_LAT, 7),
        round((hole.elevation_m or 0.0) + depth_m * math.sin(inclination), 2),
    ]


def trace_points(inclination_deg, azimuth_deg, length_m, step_m=10.0):
    """
    Return points along the hole, measured in metres FROM THE COLLAR.

        [{"depth_m": 0,  "east_m": 0.0, "north_m": 0.0, "tvd_m": 0.0}, ...]

    tvd_m is "true vertical depth" - how far straight down you actually are,
    which is less than depth_m for an angled hole.
    """
    if not length_m or length_m <= 0:
        return []
    if not step_m or step_m <= 0:
        raise ValueError(f"step_m must be positive, got {step_m!r}")  # else the loop below never ends

    # inclination is negative downwards (-90 = vertical). Work with the dip angle.
    dip = math.radians(abs(inclination_deg))
    azimuth = math.radians(azimuth_deg or 0.0)

    horizontal_per_m = math.cos(dip)
    vertical_per_m = math.sin(dip)

    points = []
    depth = 0.0
    while depth < length_m:
        horizontal = depth * horizontal_per_m
        points.append({
            "depth_m": round(depth, 2),
            "east_m": round(horizontal * math.sin(azimuth), 3),
            "north_m": round(horizontal * math.cos(azimuth), 3),
            "tvd_m": round(depth * vertical_per_m, 3),
        })
        depth += step_m

    # always include the very bottom of the hole
    horizontal = length_m * horizontal_per_m
    points.append({
        "depth_m": round(length_m, 2),
        "east_m": round(horizontal * math.sin(azimuth), 3),
        "north_m": round(horizontal * math.cos(azimuth), 3),
        "tvd_m": round(length_m * vertical_per_m, 3),
    })
    return points
