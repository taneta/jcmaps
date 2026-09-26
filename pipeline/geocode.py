"""Venue table with coordinates: known points from data/venue_points.json, else Nominatim at one request per
second, cached in site/data/geocode.json."""
from __future__ import annotations

import re
import time
from collections.abc import Callable
from pathlib import Path

import httpx

from pipeline.check import CANCELLED
from pipeline.model import Raw, Venue
from pipeline.util import ROOT, UA, normalize, read_json, slug, write_json

CACHE = ROOT / "site" / "data" / "geocode.json"  # published with the site, pulled back on the next run
POINTS = ROOT / "data" / "venue_points.json"  # venue id -> lat, lon, osm_id: pinned from here, never geocoded (#5)
STREET = "highway"  # Nominatim's category for a street; to a query with a house number that is no answer
NOMINATIM = "https://nominatim.openstreetmap.org/search"
KNOWN_CITIES = ("jersey city", "hoboken", "union city", "bayonne", "newark", "new york", "weehawken",
                "north bergen", "secaucus", "kearny", "harrison", "west new york")
ADDRESS = re.compile(r"\b\d{1,5}(?:-\d{1,5})?\s+[A-Za-z][A-Za-z\.' ]{2,40}?\b(?:Ave|Avenue|St|Street|Dr|Drive|Blvd|"
                     r"Boulevard|Pl|Place|Rd|Road|Way|Ter|Terrace|Ct|Court|Ln|Lane)\b\.?", re.I)
HOUSE = re.compile(r"\b\d+[a-z]?(?:-\d+)?\s+[^,]+")  # house number and street, up to the next comma
SHORT = {"avenue": "ave", "street": "st", "drive": "dr", "boulevard": "blvd", "place": "pl", "road": "rd",
         "terrace": "ter", "court": "ct", "lane": "ln"}


def _words(text: str) -> str:
    words = re.findall(r"[a-z0-9]+", normalize(text).replace("'", "").replace(".", ""))
    return " ".join(SHORT.get(w, w) for w in words)


def venue_key(name: str | None, address: str | None) -> str:
    """One key per place, however a source spells it: house number, street and city, lowercase, suffixes shortened,
    punctuation dropped ("295 JOHNSTON AVE., Jersey City" and "295 Johnston Ave" are "295 johnston ave, jersey city").
    An address without a house number is used whole; without an address, the name."""
    text = normalize(address or "")
    m = HOUSE.search(text)
    if not m:
        return _words(address or name or "")
    city = next((c for c in KNOWN_CITIES if c in text[m.end():]), "jersey city")  # Hoboken has a Grand St too
    return f"{_words(m.group(0))}, {city}"


def with_city(text: str) -> str:
    return text if any(c in text.lower() for c in KNOWN_CITIES) else f"{text}, Jersey City, NJ"


def candidates(name: str | None, address: str | None) -> list[str]:
    """Queries to try in order: the address, the street-number part of it, the venue name."""
    out: list[str] = []
    if address:
        out.append(with_city(address))
        m = ADDRESS.search(address)
        if m and m.group(0) != address:
            out.append(with_city(m.group(0)))
    if name and not name.lower().startswith("bookmobile stop"):
        out.append(with_city(name))
    seen: set[str] = set()
    return [c for c in out if not (normalize(c) in seen or seen.add(normalize(c)))]


def nominatim_query(client: httpx.Client, viewbox: list[float]) -> Callable[[str], tuple[float, float, str] | None]:
    """The best hit as (lat, lon, category); the category tells a building or a place from a street."""
    def query(q: str) -> tuple[float, float, str] | None:
        r = client.get(NOMINATIM, params={"q": q, "format": "jsonv2", "limit": 1,
                                          "viewbox": ",".join(str(x) for x in viewbox), "bounded": 0},
                       headers={"User-Agent": UA})
        r.raise_for_status()
        hits = r.json()
        return (float(hits[0]["lat"]), float(hits[0]["lon"]), hits[0].get("category", "")) if hits else None
    return query


class Geocoder:
    def __init__(self, query: Callable[[str], tuple[float, float, str] | None] | None, cache_path: Path = CACHE,
                 min_interval: float = 1.1):
        self.query, self.cache_path, self.min_interval = query, cache_path, min_interval
        self.cache: dict[str, list[float] | None] = read_json(cache_path, {}) or {}
        self._last = 0.0
        self.calls = 0

    def lookup(self, queries: list[str]) -> tuple[float, float] | None:
        """The first query that lands on a place. A street answer to a query with a house number is no answer: the
        pin would sit somewhere along the street, and a missing pin says more than a wrong one."""
        for q in queries:
            key = normalize(q)
            hit = self.cache.get(key)
            stale = hit is not None and len(hit) == 2  # cached before the category was kept: asked once more
            if (key not in self.cache or stale) and self.query is not None:  # offline, unknown stays unknown
                wait = self._last + self.min_interval - time.monotonic()
                if wait > 0:
                    time.sleep(wait)
                hit = self.query(q)
                self._last = time.monotonic()
                self.calls += 1
                self.cache[key] = list(hit) if hit else None
                write_json(self.cache_path, self.cache, compact=True)
            if hit and not (len(hit) == 3 and hit[2] == STREET and HOUSE.search(key)):
                return hit[0], hit[1]
        return None


def _rank(r: Raw) -> tuple[int, bool, bool]:
    """Whose name a shared venue takes: a library branch, then any other source, then a Bookmobile stop label;
    within each, labels that say cancelled last ("Bookmobile stop: Canceled- 222 Laidlaw Ave."), all caps after."""
    name = r.venue_name or r.venue_address or ""
    tier = 2 if name.startswith("Bookmobile stop") else 0 if r.source_id == "library" and not r.offsite else 1
    return tier, bool(CANCELLED.search(name)), name.isupper()


def build_venues(raws: list[Raw], geocoder: Geocoder) -> dict[str, Venue]:
    """Assign raw.venue_id and return the venue table: one venue per venue_key, named by its best record, other
    names as aliases, coordinates from the known points or else from the first query that hits. Failed lookups keep
    a venue without coordinates."""
    points = read_json(POINTS, {}) or {}
    groups: dict[str, list[Raw]] = {}
    for r in raws:
        if r.venue_name or r.venue_address:
            groups.setdefault(venue_key(r.venue_name, r.venue_address), []).append(r)
    venues: dict[str, Venue] = {}
    for key, group in groups.items():
        group.sort(key=_rank)
        names: dict[str, str] = {}
        for r in group:
            names.setdefault(normalize(r.venue_name or r.venue_address), r.venue_name or r.venue_address)
        name, *aliases = names.values()
        vid = slug(key)[:80]
        known = points.get(vid)
        hit = ((known["lat"], known["lon"]) if known
               else geocoder.lookup(list(dict.fromkeys(q for r in group for q in candidates(r.venue_name, r.venue_address)))))
        venues[vid] = Venue(id=vid, name=name, aliases=aliases, address=next((r.venue_address for r in group if r.venue_address), None),
                            lat=hit[0] if hit else None, lon=hit[1] if hit else None,
                            kind="library" if _rank(group[0])[0] == 0 else None, osm_id=known.get("osm_id") if known else None)
        for r in group:
            r.venue_id = vid
    return venues
