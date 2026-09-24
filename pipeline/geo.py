"""Point in polygon and distance, without a GIS dependency."""
from __future__ import annotations

from math import asin, cos, radians, sin, sqrt


def inside(lat: float, lon: float, ring: list[list[float]]) -> bool:
    """Ray casting over a ring of [lon, lat] points."""
    hit = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        if (y1 > lat) != (y2 > lat):
            x = x1 + (lat - y1) * (x2 - x1) / (y2 - y1)
            if lon < x:
                hit = not hit
    return hit


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = radians(lat1), radians(lat2)
    dp, dl = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return 2 * 6371000 * asin(sqrt(a))
