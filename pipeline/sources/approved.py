"""Events the owner approved from the suggestion form, kept as a short list in the repo (data/approved_events.json):
event facts only, never who suggested them. An entry publishes like any feed's event and drops off by itself once it
is over. The list is read like a feed, from its path, so the cache and the fixtures work as for any source."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import httpx

from pipeline.model import Evidence, Raw
from pipeline.util import ROOT, TZ, sha


def fetch(source_id: str, url: str, cache_dir: Path, client: httpx.Client | None) -> str:
    """url is the list's path in the repo; a copy goes to the cache like a downloaded feed."""
    text = (ROOT / url).read_text()
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / f"{source_id}.json").write_text(text)
    return text


def parse(text: str, src: dict) -> list[Raw]:
    """Each entry: title, start and end in Jersey City time (2026-10-05T14:00), place, address, link, price (free or
    paid), kids (yes or no), description, and an organization's name as organizer. What the owner decided stands as
    a rule; what is left out, the model may still fill from the description."""
    raws: list[Raw] = []
    for e in json.loads(text):
        local = lambda s: datetime.fromisoformat(s).replace(tzinfo=TZ).astimezone(timezone.utc)
        decided = {k: e[k] for k in ("price", "kids") if e.get(k) in ("free", "paid", "yes", "no")}
        raws.append(Raw(
            source_id=src["id"], source_uid=sha(f"{e['title']}|{e['start']}"), title=e["title"], url=e.get("link") or src["link"],
            description=e.get("description", ""), venue_name=e.get("place"), venue_address=e.get("address"),
            organizer_name=e.get("organizer"), start_utc=local(e["start"]), end_utc=local(e["end"]) if e.get("end") else None,
            date=e["start"][:10], price=decided.get("price", "unknown"), kid_friendly=decided.get("kids", "unknown"),
            evidence={"kid_friendly" if k == "kids" else k: Evidence(quote="approved by the owner", from_="rule") for k in decided},
        ))
    return raws
