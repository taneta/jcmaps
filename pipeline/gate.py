"""The publish gate: what a candidate snapshot must pass before it replaces the last good one."""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from pipeline.geo import inside
from pipeline.model import Snapshot

def gate(candidate: Snapshot, boundary: list[list[float]], now: datetime) -> list[str]:
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
    return reasons


# OpenAI keys are sk-... with mixed case and digits; a lowercase URL slug such as "desk-lamp-workshop-2026" is not one.
SECRET_SHAPES = [re.compile(x) for x in (r"\bsk-(?=[A-Za-z0-9_-]{20,})(?=[A-Za-z0-9_-]*[A-Z0-9])[A-Za-z0-9_-]+",
                                         r"\bgh[pousr]_[A-Za-z0-9]{30,}", r"github_pat_[A-Za-z0-9_]{20,}", r"OPENAI_API_KEY\s*=")]


def looks_secret(text: str) -> bool:
    return any(p.search(text) for p in SECRET_SHAPES)


def secret_scan(texts: dict[str, str]) -> list[str]:
    """Names of texts that contain something shaped like an API key or token. Everything under site/ is public."""
    return [f"secret-shaped string in {name}" for name, text in texts.items() if looks_secret(text)]
