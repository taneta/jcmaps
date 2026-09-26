"""Modern Campus calendars (Hudson County Community College's), read from their JSON events endpoint: the iCal twin
carries neither categories nor links. The source's city.json entry gives the endpoint, the categories to keep, the
campuses' addresses and the calendar page to link to. Meeting links and passcodes in a description are removed as
the feed is read (docs/sources.md, rule 9)."""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from pipeline.model import Raw
from pipeline.sources.ical import ONLINE
from pipeline.util import TZ, now_utc, scrub

MEETING = re.compile(r"https?://\S*(?:zoom\.us|webex\.com|teams\.microsoft\.com|meet\.google\.com)\S*"
                     r"|\b(?:passcode|password|meeting id)\s*[:#]?\s*\S+", re.I)


def fetch(source_id: str, url: str, cache_dir: Path, client: httpx.Client) -> str:
    today = now_utc().date()
    r = client.get(url, params={"start": today.isoformat(), "end": (today + timedelta(days=32)).isoformat()})
    r.raise_for_status()
    text = scrub(r.text)
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / f"{source_id}.json").write_text(text)
    return text


def parse(text: str, src: dict) -> list[Raw]:
    """Entries in the source's categories, with a start, at a campus the source's places name (a video call, an
    off-campus outing or an unnamed place is left out). The room goes into the venue name. Times come in UTC
    without a zone."""
    keep, places = set(src.get("categories", [])), src.get("places", {})
    utc = lambda s: datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
    raws: list[Raw] = []
    for e in json.loads(text):
        location, room = (e.get("location") or "").strip(), (e.get("locationRoom") or "").strip()
        address = places.get(location)
        if (keep and e.get("categoryName") not in keep) or not e.get("startDatetime") or not address or ONLINE.fullmatch(location):
            continue
        start = utc(e["startDatetime"])
        raws.append(Raw(
            source_id=src["id"], source_uid=f"{e['id']}@{e['startDatetime'][:10]}" if e.get("recurring") else e["id"],
            title=e["title"].strip(), url=e.get("ticketUrl") or src["link"],
            description=MEETING.sub("", e.get("descriptionText") or "").strip(), categories=[e["categoryName"]],
            venue_name=f"{room}, {location}" if room and room != location else location, venue_address=address,
            organizer_name=src.get("name"), start_utc=start, end_utc=utc(e["endDatetime"]) if e.get("endDatetime") else None,
            date=start.astimezone(TZ).date().isoformat(), topics=[e["categoryName"]],
        ))
    return raws
