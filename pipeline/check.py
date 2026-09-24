"""Rules only: required fields, future, horizon, boundary, cancelled titles, duplicates."""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timedelta
from difflib import SequenceMatcher

from pipeline.geo import distance_m, inside
from pipeline.model import Raw, Venue
from pipeline.util import normalize

CANCELLED = re.compile(r"\b(cancel+ed|postponed)\b", re.I)
CLOSURE = re.compile(r"^\W*(library\s+|branch\s+|all\s+branches\s+)?closed\b", re.I)  # a closure notice is not an event
DEFAULT_LENGTH = timedelta(hours=2)
HORIZON = timedelta(days=31)


def status_of(raw: Raw) -> str:
    return "cancelled" if CANCELLED.search(raw.title) else "scheduled"


def _split(raws: list[Raw], reason_of) -> tuple[list[Raw], list[dict]]:
    kept, drops = [], []
    for r in raws:
        reason = reason_of(r)
        if reason:
            drops.append({"id": r.id, "title": r.title, "reason": reason})
        else:
            kept.append(r)
    return kept, drops


def prefilter(raws: list[Raw], now: datetime) -> tuple[list[Raw], list[dict]]:
    """Before enrichment, so the model never sees past or far-future entries."""
    def reason_of(r: Raw) -> str | None:
        end = r.end_utc or r.start_utc + DEFAULT_LENGTH
        if not (r.title and r.url):
            return "missing_field"
        if CLOSURE.search(r.title):
            return "closure"
        if end < now:
            return "past"
        if r.start_utc > now + HORIZON:
            return "beyond_horizon"
        return None
    return _split(raws, reason_of)


def check(raws: list[Raw], venues: dict[str, Venue], boundary: list[list[float]]) -> tuple[list[Raw], list[dict]]:
    """After geocoding: boundary, then duplicates."""
    def reason_of(r: Raw) -> str | None:
        v = venues.get(r.venue_id or "")
        if v and v.lat is not None and not inside(v.lat, v.lon, boundary):
            return "outside_boundary"
        return None
    kept, drops = _split(raws, reason_of)
    kept, dup_drops = dedupe(kept, venues)
    return kept, drops + dup_drops


def _near(a: Raw, b: Raw, venues: dict[str, Venue]) -> bool:
    va, vb = venues.get(a.venue_id or ""), venues.get(b.venue_id or "")
    if va and vb and va.lat is not None and vb.lat is not None:
        return distance_m(va.lat, va.lon, vb.lat, vb.lon) <= 150
    return a.venue_id is not None and a.venue_id == b.venue_id


def dedupe(raws: list[Raw], venues: dict[str, Venue]) -> tuple[list[Raw], list[dict]]:
    """Same date, start within 30 minutes, within 150 m, similar title: the record with more evidence wins."""
    by_date: dict[str, list[Raw]] = defaultdict(list)
    for r in raws:
        by_date[r.date].append(r)
    gone: set[int] = set()
    drops: list[dict] = []
    for group in by_date.values():
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                if id(a) in gone or id(b) in gone:
                    continue
                if abs((a.start_utc - b.start_utc).total_seconds()) > 1800 or not _near(a, b, venues):
                    continue
                if SequenceMatcher(None, normalize(a.title), normalize(b.title)).ratio() < 0.8:
                    continue
                winner, loser = (a, b) if len(a.evidence) >= len(b.evidence) else (b, a)
                gone.add(id(loser))
                winner.alt_urls.append(loser.url)
                drops.append({"id": loser.id, "title": loser.title, "reason": "duplicate", "of": winner.id})
    return [r for r in raws if id(r) not in gone], drops
