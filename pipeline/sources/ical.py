"""Any single public iCal feed, read the same way: the city's calendar first, then a college's, a team's or a group's.
The source's city.json entry gives the feed URL and, for feeds without links, a link template."""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import httpx
from dateutil.rrule import rrulestr
from icalendar import Calendar

from pipeline.model import Raw
from pipeline.util import TZ, now_utc, scrub, strip_html

# A location that is only a video call, or nothing at all, has no place: the event is listed without a pin.
ONLINE = re.compile(r"(?:(?:via |on )?(?:zoom|online|virtual(?:ly)?|webinar|livestream|teams|google meet)\b[^0-9]*)?",
                    re.I)
HOUSE = re.compile(r"\b\d{1,5}[A-Za-z]?(?:-\d{1,5})?\s+(?=[A-Za-z])")  # where a street address starts: "280 Grove"


def fetch(source_id: str, url: str, cache_dir: Path, client: httpx.Client) -> str:
    r = client.get(url)
    r.raise_for_status()
    text = scrub(re.sub(r"\r?\n[ \t]", "", r.text))  # unfolded first, so a contact split across lines is caught too
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / f"{source_id}.ics").write_text(text)
    return text


def categories(ev) -> list[str]:
    raw = ev.get("CATEGORIES")
    if raw is None:
        return []
    items = raw if isinstance(raw, list) else [raw]
    out: list[str] = []
    for item in items:
        out.extend(str(c) for c in getattr(item, "cats", [item]))
    return [c.strip() for c in out if c.strip()]


def _utc(dt: datetime) -> datetime:
    return (dt if dt.tzinfo else dt.replace(tzinfo=TZ)).astimezone(timezone.utc)


def span(start: date | datetime, end: date | datetime | None) -> tuple[datetime, datetime | None, bool, str]:
    """Start and end in UTC, all-day, and the local date. Date-only entries are all-day and their end is exclusive;
    times without a zone are Jersey City time."""
    if isinstance(start, datetime):
        s = _utc(start)
        return s, _utc(end) if isinstance(end, datetime) else None, False, s.astimezone(TZ).date().isoformat()
    e = end if isinstance(end, date) and not isinstance(end, datetime) else start + timedelta(days=1)
    return (datetime.combine(start, time(0), TZ).astimezone(timezone.utc),
            datetime.combine(e, time(0), TZ).astimezone(timezone.utc), True, start.isoformat())


def address(text: str) -> str:
    """Tidy a free-text address for the geocoder's key (house number, street, city): "280 Grove St. Jersey City NJ
    07302" becomes "280 Grove St., Jersey City NJ 07302", and a cut-off ZIP ("NJ 0730") is dropped."""
    text = re.sub(r"\s+,", ",", text)
    text = re.sub(r",?\s+(Jersey City)\b", r", \1", text, flags=re.I)
    return re.sub(r"\b(NJ)\s+\d{1,4}$", r"\1", text).strip(" ,.")


def place(location: str, places: dict[str, str]) -> tuple[str | None, str | None]:
    """A free-text LOCATION as (venue name, address). The address starts at the house number. A place the source's
    config names, such as City Hall, gets the address given there. A video call or nothing gets no venue."""
    text = re.sub(r"\s+", " ", location).strip(" ,.")
    if ONLINE.fullmatch(text):
        return None, None
    m = HOUSE.search(text)
    if m:
        return text[:m.start()].strip(" ,") or None, address(text[m.start():])
    # the longest name that appears wins: "City Hall Annex" names the annex's building, not City Hall
    known = max((name for name in places if name.lower() in text.lower()), key=len, default=None)
    return (known, places[known]) if known else (text, None)


def _stamp(d: date | datetime) -> str:
    """A start as a key in Jersey City time: 20261004T0900, or 20261004 for a whole day."""
    if not isinstance(d, datetime):
        return d.strftime("%Y%m%d")
    return (d.astimezone(TZ) if d.tzinfo else d).strftime("%Y%m%dT%H%M")


def starts(ev, window: tuple[datetime, datetime]) -> list[date | datetime]:
    """DTSTART; for a repeating event, every start inside the window except its EXDATEs."""
    start = ev.decoded("DTSTART")
    rule = ev.get("RRULE")
    if rule is None:
        return [start]
    rule = rule[0] if isinstance(rule, list) else rule
    anchor = start if isinstance(start, datetime) else datetime.combine(start, time(0))
    lo, hi = window
    if anchor.tzinfo is None:  # floating and all-day starts are compared in Jersey City time
        lo, hi = (w.astimezone(TZ).replace(tzinfo=None) for w in window)
    parts = rule.to_ical().decode().split(";")
    if any(p.startswith("UNTIL=") for p in parts):  # RFC 5545 forbids COUNT with UNTIL; the city's feed has both
        parts = [p for p in parts if not p.startswith("COUNT=")]
    try:
        found = rrulestr(";".join(parts), dtstart=anchor).between(lo, hi, inc=True)
    except (ValueError, TypeError):  # a rule dateutil refuses stands for its first date
        return [start]
    exdates = ev.get("EXDATE") or []
    skip = {_stamp(d.dt) for x in (exdates if isinstance(exdates, list) else [exdates]) for d in x.dts}
    found = [d if isinstance(start, datetime) else d.date() for d in found]
    return [d for d in found if _stamp(d) not in skip]


def parse(text: str, src: dict, window: tuple[datetime, datetime] | None = None) -> list[Raw]:
    """src is the source's city.json entry: id, name, and optionally link (a template with {uid}), places (name to
    address), categories (keep only entries with one of them) and keep (patterns an entry's properties must match,
    such as SUMMARY and LOCATION: a team's home games). Repeating events are expanded inside the window, by default
    from yesterday to a month ahead, and each date becomes its own record."""
    now = now_utc()
    window = window or (now - timedelta(days=1), now + timedelta(days=32))
    only = {c.lower() for c in src.get("categories", [])}
    keep = {prop: re.compile(rx, re.I) for prop, rx in src.get("keep", {}).items()}
    out: dict[str, Raw] = {}
    events = Calendar.from_ical(text).walk("VEVENT")
    for ev in sorted(events, key=lambda e: "RECURRENCE-ID" in e):  # a changed date replaces the one its rule made
        title, uid = str(ev.get("SUMMARY", "")).strip(), str(ev.get("UID", "")).strip()
        cats = categories(ev)
        changed = f"{uid}@{_stamp(ev.decoded('RECURRENCE-ID'))}" if "RECURRENCE-ID" in ev else None
        if (not title or not uid or str(ev.get("STATUS", "")).upper() == "CANCELLED"
                or str(ev.get("CLASS", "")).upper() in {"PRIVATE", "CONFIDENTIAL"}
                or (only and not only & {c.lower() for c in cats})
                or not all(rx.search(str(ev.get(prop, ""))) for prop, rx in keep.items())):
            if changed:  # one cancelled date of a repeating event
                out.pop(changed, None)
            continue
        first = ev.decoded("DTSTART")
        end = ev.decoded("DTEND") if "DTEND" in ev else first + ev.decoded("DURATION") if "DURATION" in ev else None
        try:
            length = end - first if end is not None else None
        except TypeError:  # a date and a date-time: keep the start only
            length = None
        venue_name, venue_address = place(str(ev.get("LOCATION", "")), src.get("places", {}))
        url = str(ev.get("URL", "")).strip() or src.get("link", "").format(uid=uid)
        repeats = "RRULE" in ev
        for s in starts(ev, window):
            key = changed or (f"{uid}@{_stamp(s)}" if repeats or uid in out else uid)
            start_utc, end_utc, all_day, day = span(s, s + length if length is not None else None)
            out[key] = Raw(
                source_id=src["id"], source_uid=key, title=title, url=url,
                description=strip_html(str(ev.get("DESCRIPTION", ""))), categories=cats,
                venue_name=venue_name, venue_address=venue_address, organizer_name=src.get("name"),
                start_utc=start_utc, end_utc=end_utc, all_day=all_day, date=day, topics=sorted(set(cats)),
            )
    return list(out.values())
