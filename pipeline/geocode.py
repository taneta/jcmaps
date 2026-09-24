"""Venue table with coordinates. Nominatim at one request per second, cached in data/geocode.json."""
from __future__ import annotations

import re
import time
from collections.abc import Callable
from pathlib import Path

import httpx

from pipeline.model import Raw, Venue
from pipeline.util import ROOT, UA, normalize, read_json, slug, write_json

CACHE = ROOT / "site" / "data" / "geocode.json"  # published with the site, pulled back on the next run
NOMINATIM = "https://nominatim.openstreetmap.org/search"
KNOWN_CITIES = ("jersey city", "hoboken", "union city", "bayonne", "newark", "new york", "weehawken",
                "north bergen", "secaucus", "kearny", "harrison", "west new york")
STREET = re.compile(r"\b\d{1,5}(?:-\d{1,5})?\s+[A-Za-z][A-Za-z\.' ]{2,40}?\b(?:Ave|Avenue|St|Street|Dr|Drive|Blvd|"
                    r"Boulevard|Pl|Place|Rd|Road|Way|Ter|Terrace|Ct|Court|Ln|Lane)\b\.?", re.I)


def with_city(text: str) -> str:
    return text if any(c in text.lower() for c in KNOWN_CITIES) else f"{text}, Jersey City, NJ"


def candidates(name: str | None, address: str | None) -> list[str]:
    """Queries to try in order: the address, the street-number part of it, the venue name."""
    out: list[str] = []
    if address:
        out.append(with_city(address))
        m = STREET.search(address)
        if m and m.group(0) != address:
            out.append(with_city(m.group(0)))
    if name and not name.lower().startswith("bookmobile stop"):
        out.append(with_city(name))
    seen: set[str] = set()
    return [c for c in out if not (normalize(c) in seen or seen.add(normalize(c)))]


def nominatim_query(client: httpx.Client, viewbox: list[float]) -> Callable[[str], tuple[float, float] | None]:
    def query(q: str) -> tuple[float, float] | None:
        r = client.get(NOMINATIM, params={"q": q, "format": "jsonv2", "limit": 1,
                                          "viewbox": ",".join(str(x) for x in viewbox), "bounded": 0},
                       headers={"User-Agent": UA})
        r.raise_for_status()
        hits = r.json()
        return (float(hits[0]["lat"]), float(hits[0]["lon"])) if hits else None
    return query


class Geocoder:
    def __init__(self, query: Callable[[str], tuple[float, float] | None] | None, cache_path: Path = CACHE,
                 min_interval: float = 1.1):
        self.query, self.cache_path, self.min_interval = query, cache_path, min_interval
        self.cache: dict[str, list[float] | None] = read_json(cache_path, {}) or {}
        self._last = 0.0
        self.calls = 0

    def lookup(self, queries: list[str]) -> tuple[float, float] | None:
        for q in queries:
            key = normalize(q)
            if key not in self.cache:
                if self.query is None:  # offline: unknown stays unknown
                    continue
                wait = self._last + self.min_interval - time.monotonic()
                if wait > 0:
                    time.sleep(wait)
                hit = self.query(q)
                self._last = time.monotonic()
                self.calls += 1
                self.cache[key] = list(hit) if hit else None
                write_json(self.cache_path, self.cache, compact=True)
            if self.cache[key]:
                return tuple(self.cache[key])  # type: ignore[return-value]
        return None


def build_venues(raws: list[Raw], geocoder: Geocoder) -> dict[str, Venue]:
    """Assign raw.venue_id and return the venue table. Failed lookups keep a venue without coordinates."""
    venues: dict[str, Venue] = {}
    for r in raws:
        if not (r.venue_name or r.venue_address):
            continue
        vid = slug(f"{r.venue_name or ''} {r.venue_address or ''}")[:80]
        if vid not in venues:
            hit = geocoder.lookup(candidates(r.venue_name, r.venue_address))
            venues[vid] = Venue(id=vid, name=r.venue_name or r.venue_address or "", address=r.venue_address,
                                lat=hit[0] if hit else None, lon=hit[1] if hit else None,
                                kind="library" if r.source_id == "library" and not r.venue_name.startswith("Bookmobile") else None)
        r.venue_id = vid
    return venues
