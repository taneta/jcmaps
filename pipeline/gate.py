"""The publish gate: a candidate snapshot is compared with the last good one before it replaces it."""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from pipeline.geo import inside
from pipeline.model import Snapshot

SHRINK = 0.30  # a source losing more than this share of its events fails the gate
MIN_BASE = 10  # unless the previous count was too small to judge


def gate(candidate: Snapshot, previous: dict | None, boundary: list[list[float]], now: datetime,
         failed: set[str] = frozenset()) -> list[str]:
    """failed: sources whose fetch raised. Their carried events are judged like fresh ones; a failed source with
    nothing left to carry is down, which the report and the issue say, not a shrink."""
    reasons: list[str] = []
    grace = now - timedelta(hours=1)
    for o in candidate.occurrences:
        end = o.end_utc or o.start_utc + timedelta(hours=2)
        if end < grace:
            reasons.append(f"past occurrence: {o.event_id}")
            break
    for v in candidate.venues:
        if v.lat is not None and not inside(v.lat, v.lon, boundary):
            reasons.append(f"pin outside boundary: {v.id}")
            break
    if not candidate.events:
        reasons.append("no events at all")
    for sid, old in (previous or {}).get("sources", {}).items():
        before, after = old.get("count", 0), candidate.sources.get(sid, {}).get("count", 0)
        if before >= MIN_BASE and after < before * (1 - SHRINK) and not (sid in failed and after == 0):
            reasons.append(f"source {sid} shrank from {before} to {after}")
    return reasons


# OpenAI keys are sk-... with mixed case and digits; a lowercase URL slug such as "desk-lamp-workshop-2026" is not one.
SECRET_SHAPES = [re.compile(x) for x in (r"\bsk-(?=[A-Za-z0-9_-]{20,})(?=[A-Za-z0-9_-]*[A-Z0-9])[A-Za-z0-9_-]+",
                                         r"\bgh[pousr]_[A-Za-z0-9]{30,}", r"github_pat_[A-Za-z0-9_]{20,}", r"OPENAI_API_KEY\s*=")]


def looks_secret(text: str) -> bool:
    return any(p.search(text) for p in SECRET_SHAPES)


def secret_scan(texts: dict[str, str]) -> list[str]:
    """Names of texts that contain something shaped like an API key or token. Everything under site/ is public."""
    return [f"secret-shaped string in {name}" for name, text in texts.items() if looks_secret(text)]
