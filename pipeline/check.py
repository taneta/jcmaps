"""Rules only: required fields, future, horizon, boundary, cancelled titles, duplicates."""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timedelta
from difflib import SequenceMatcher

from pipeline.geo import inside
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
    kept, dup_drops = dedupe(kept)
    return kept, drops + dup_drops


def _overlap(a: Raw, b: Raw) -> bool:
    """A missing end means two hours, as in the search rules."""
    return (a.start_utc < (b.end_utc or b.start_utc + DEFAULT_LENGTH)
            and b.start_utc < (a.end_utc or a.start_utc + DEFAULT_LENGTH))


def _same_title(a: str, b: str) -> bool:
    """Similar, or one starts with the other's first three words ("What We Keep 2026" and
    "WHAT WE KEEP: Artist Talk & Mini-photobook Workshop")."""
    if SequenceMatcher(None, normalize(a), normalize(b)).ratio() >= 0.8:
        return True
    wa, wb = re.findall(r"[a-z0-9]+", normalize(a)), re.findall(r"[a-z0-9]+", normalize(b))
    n = min(3, len(wa), len(wb))
    return n > 0 and wa[:n] == wb[:n]


def dedupe(raws: list[Raw]) -> tuple[list[Raw], list[dict]]:
    """Same venue, same date, overlapping times, same title: the record with more evidence wins and keeps every URL."""
    groups: dict[tuple[str, str], list[Raw]] = defaultdict(list)
    for r in raws:
        if r.venue_id:
            groups[(r.venue_id, r.date)].append(r)
    gone: set[int] = set()
    drops: list[dict] = []
    # A run or an exhibition listed as one span, at a venue where another source lists its dates: the dates win,
    # and each of them carries the span's link (a carried record already holds it from the last run).
    for a in [r for r in raws if id(r) not in gone and r.venue_id and _days(r) > 1]:
        showings = [b for b in raws if id(b) not in gone and b is not a and b.venue_id == a.venue_id and _days(b) <= 1
                    and a.start_utc <= b.start_utc <= a.end_utc and _same_title(a.title, b.title)]
        if showings:
            gone.add(id(a))
            for b in showings:
                if a.url not in b.alt_urls:
                    b.alt_urls.append(a.url)
            drops.append({"id": a.id, "title": a.title, "reason": "duplicate", "of": showings[0].id})
    for group in groups.values():
        group.sort(key=lambda r: len(r.evidence), reverse=True)  # so the first of two duplicates is the winner
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                if id(a) in gone or id(b) in gone or not (_overlap(a, b) and _same_title(a.title, b.title)):
                    continue
                gone.add(id(b))
                a.alt_urls.append(b.url)
                drops.append({"id": b.id, "title": b.title, "reason": "duplicate", "of": a.id})
    return [r for r in raws if id(r) not in gone], drops


def _days(r: Raw) -> float:
    return ((r.end_utc or r.start_utc) - r.start_utc) / timedelta(days=1)
