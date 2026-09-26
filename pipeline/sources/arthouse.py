"""Art House Productions' upcoming events: a Shopify collection read as JSON. The title carries the name and the
date or the run ("RENT: The Musical | September 24 - October 18, 2026"), the body text the time and, for a few, a
place. The $0 variant price is a placeholder (tickets are sold elsewhere), so the price is what the text says."""
from __future__ import annotations

import json
import re
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import httpx

from pipeline.model import Raw
from pipeline.util import TZ, scrub, strip_html

MONTHS = {m: i for i, m in enumerate(("january", "february", "march", "april", "may", "june", "july", "august",
                                      "september", "october", "november", "december"), 1)}
DATES = re.compile(r"(?P<m1>[A-Za-z]+) (?P<d1>\d{1,2})(?:\s*[-–]\s*(?P<m2>[A-Za-z]+) (?P<d2>\d{1,2}))?,? (?P<y>\d{4})")
CLOCK = re.compile(r"\bat (\d{1,2})(?::(\d{2}))?\s*([ap])\.?m\b", re.I)


def fetch(source_id: str, url: str, cache_dir: Path, client: httpx.Client) -> str:
    r = client.get(url)
    r.raise_for_status()
    text = scrub(r.text)
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / f"{source_id}.json").write_text(text)
    return text


def days(text: str) -> tuple[date, date] | None:
    """"September 24 - October 18, 2026" as first and last day, a single date twice, None without a day."""
    m = DATES.search(text)
    if not m or m["m1"].lower() not in MONTHS or (m["m2"] and m["m2"].lower() not in MONTHS):
        return None
    first = date(int(m["y"]), MONTHS[m["m1"].lower()], int(m["d1"]))
    last = date(int(m["y"]), MONTHS[m["m2"].lower()], int(m["d2"])) if m["m2"] else first
    return first, last


def parse(text: str, src: dict) -> list[Raw]:
    """One record per product with a date. A run of days is one all-day span (an exhibition, or a show's run, which
    the duplicate rule folds into another source's dated showings); a single day starts at the time the text gives,
    else lasts the day. The venue is the source's own unless the text names one of its places."""
    venue, places = src["venue"], src.get("places", {})
    raws: list[Raw] = []
    for p in json.loads(text)["products"]:
        name, _, rest = p["title"].partition(" | ")
        span = days(rest)
        if not span:
            continue
        first, last = span
        body = strip_html(p.get("body_html") or "")
        clock = CLOCK.search(body) if first == last else None
        if clock:
            hour = int(clock.group(1)) % 12 + (12 if clock.group(3).lower() == "p" else 0)
            start = datetime.combine(first, time(hour, int(clock.group(2) or 0)), TZ).astimezone(timezone.utc)
            end, all_day = None, False
        else:
            start = datetime.combine(first, time(0), TZ).astimezone(timezone.utc)
            end, all_day = datetime.combine(last + timedelta(days=1), time(0), TZ).astimezone(timezone.utc), True
        known = next((n for n in places if n.lower() in f"{name} {body}".lower()), None)
        raws.append(Raw(
            source_id=src["id"], source_uid=str(p["id"]), title=name.strip(), url=src["link"].format(handle=p["handle"]),
            description=body, categories=[t for t in p.get("tags", []) if t],
            venue_name=known or venue["name"], venue_address=places[known] if known else venue["address"],
            organizer_name=venue["name"], start_utc=start, end_utc=end, all_day=all_day, date=first.isoformat(),
        ))
    return raws
