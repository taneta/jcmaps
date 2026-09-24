"""Point in polygon, without a GIS dependency."""
from __future__ import annotations


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
