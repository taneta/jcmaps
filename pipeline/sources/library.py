"""Jersey City Free Public Library: one LibCal iCal feed per calendar (branch)."""
from __future__ import annotations

import re
from pathlib import Path

import httpx
from icalendar import Calendar

from pipeline.model import Evidence, Raw
from pipeline.sources.ical import categories, span

SOURCE_ID = "library"
FEED = "https://jclibrary.libcal.com/ical_subscribe.php?src=p&cid={cid}"
KID_YES = {"Storytime Events", "Children Events", "All-Ages Events", "Family Events", "Teen Programs",
           "Babies & Toddlers (0-2 Years)"}
KID_NO = {"Older Adults Events"}
NOISE = re.compile(r"^(January|February|March|April|May|June|July|August|September|October|November|December"
                   r"|Blue Schedule|Red Schedule|Popular Events|Other/Multidisciplinary)$")
# Talk of money leaves the price to the model: a price, a fee, a cost, a fundraiser, or a ticket in a sentence about
# buying it (branches also hand out free entry tickets, #17). The word "free" decides nothing on its own: it is in the
# library's name, "Jersey City Free Public Library" (#24).
MONEY = re.compile(r"\$\s?\d|\bfees?\b|\bcosts?\b|\bfundrais\w*"
                   r"|\btickets?\b[^.!?\n]*\b(?:buy|bought|purchas\w*|sold|sell\w*|sales?|price\w*)\b"
                   r"|\b(?:buy|bought|purchas\w*|sold|sell\w*)\b[^.!?\n]*\btickets?\b", re.I)
BOOKMOBILE_STOP = re.compile(r"^(?P<place>.+?)\s*-\s*[^-]*?,?\s*Bookmobile Stop\s*$", re.I)


def fetch(cid: str, cache_dir: Path, client: httpx.Client) -> str:
    r = client.get(FEED.format(cid=cid))
    r.raise_for_status()
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / f"{cid}.ics").write_text(r.text)
    return r.text


def parse(text: str, cid: str, branch: dict | None) -> list[Raw]:
    """branch: {"name", "address"} for a fixed calendar, None for Bookmobile and Spotlight."""
    cal = Calendar.from_ical(text)
    calname = str(cal.get("X-WR-CALNAME", "")).strip()
    raws: list[Raw] = []
    for ev in cal.walk("VEVENT"):
        title = str(ev.get("SUMMARY", "")).strip()
        uid = str(ev.get("UID", "")).split("-")[-1]
        if not title or not uid:
            continue
        cats = categories(ev)
        short = [c.split(">")[-1].strip() for c in cats]
        topics = sorted({c for c in short if not NOISE.match(c)})
        description = str(ev.get("DESCRIPTION", "")).strip()
        location = str(ev.get("LOCATION", "")).strip()
        start, end, all_day, day = span(ev.decoded("DTSTART"), ev.decoded("DTEND") if "DTEND" in ev else None)

        venue_name, venue_address, offsite = None, None, False
        if calname.lower().startswith("bookmobile"):
            m = BOOKMOBILE_STOP.match(title)
            if m:
                venue_name = f"Bookmobile stop: {m.group('place').strip()}"
                venue_address = m.group("place").strip()
            else:
                offsite = True
        elif "offsite" in location.lower() or branch is None:
            offsite = True
        else:
            venue_name, venue_address = branch["name"], branch.get("address")

        evidence: dict[str, Evidence] = {}
        kid = "unknown"
        if any(c in KID_YES for c in short):
            kid = "yes"
            evidence["kid_friendly"] = Evidence(quote=next(c for c in short if c in KID_YES).lower(), from_="categories")
        elif any(c in KID_NO for c in short):
            kid = "no"
            evidence["kid_friendly"] = Evidence(quote=next(c for c in short if c in KID_NO).lower(), from_="categories")
        price = "unknown"
        if not (MONEY.search(title) or MONEY.search(description)):
            price = "free"
            evidence["price"] = Evidence(quote="library program", from_="rule")
        evidence["organizer_type"] = Evidence(quote="public library", from_="rule")

        raws.append(Raw(
            source_id=SOURCE_ID, source_uid=uid, title=title, url=str(ev.get("URL", "")),
            description=description, categories=cats, cost_text=None,
            venue_name=venue_name, venue_address=venue_address, organizer_name="Jersey City Free Public Library",
            start_utc=start, end_utc=end, all_day=all_day, date=day, offsite=offsite,
            kid_friendly=kid, price=price, organizer_type="city", topics=topics, evidence=evidence,
        ))
    return raws
