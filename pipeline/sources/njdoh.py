"""The New Jersey Department of Health's community calendar: a statewide CSV of clinics and health events, read for
the ones at a Jersey City venue. Four columns name people (who submitted the event, whom to contact); they are
dropped as the file is downloaded, before the cache, so nothing downstream sees them (docs/sources.md, rule 9)."""
from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import httpx

from pipeline.model import Raw
from pipeline.util import TZ, scrub, sha

PAGE = "https://www.nj.gov/health/community-calendar/"
PERSONAL = {"Submitter_Name", "Submitter_Email", "Contact_Phone", "Contact_Email"}
LINK = re.compile(r"https?://\S+")
CLOCK = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*([AP]M)", re.I)


def fetch(source_id: str, url: str, cache_dir: Path, client: httpx.Client) -> str:
    r = client.get(url)
    r.raise_for_status()
    reader = csv.DictReader(io.StringIO(r.content.decode("utf-8-sig")))
    out = io.StringIO()
    writer = csv.DictWriter(out, [c for c in reader.fieldnames if c not in PERSONAL], extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows(reader)
    text = scrub(out.getvalue())
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / f"{source_id}.csv").write_text(text)
    return text


def when(day: str, clock: str | None) -> datetime | None:
    """"9/26/2026" with "11:00 AM" (or "1:00PM", "9 am") as a UTC datetime; None when the time is missing or odd."""
    m = CLOCK.search(clock or "")
    if not m:
        return None
    hour = int(m.group(1)) % 12 + (12 if m.group(3).upper() == "PM" else 0)
    local = datetime.strptime(day, "%m/%d/%Y").replace(hour=hour, minute=int(m.group(2) or 0), tzinfo=TZ)
    return local.astimezone(timezone.utc)


def parse(text: str, src: dict) -> list[Raw]:
    """Reviewed rows open to the public at a Jersey City venue. The link is the registration link, else the extra
    link, else the calendar page; the registration column's words go into the description, since they often say
    whether to register or walk in."""
    raws: list[Raw] = []
    for row in csv.DictReader(io.StringIO(text)):
        if (row.get("Review_Status") != "Approved" or row.get("General_Public") != "Yes"
                or "jersey city" not in (row.get("Venue_City") or "").lower()):
            continue
        start = when(row["Event_Date"], row.get("Start_Time"))
        if start is None:
            continue
        link = next((m.group(0) for f in ("Registration_Link", "Additional_Link") if (m := LINK.search(row.get(f) or ""))), PAGE)
        services = row.get("Services") or ""  # a JSON list in a cell: ["Vaccine clinic"]
        cats = json.loads(services) if services.startswith("[") else [s.strip() for s in services.split(",") if s.strip()]
        raws.append(Raw(
            source_id=src["id"], source_uid=sha(f"{row['Event_Name']}|{row['Event_Date']}|{row.get('Venue_Address')}"),
            title=row["Event_Name"].strip(), url=link,
            description="\n".join(x.strip() for x in (row.get("Event_Description"), ", ".join(cats), row.get("Additional_Info"),
                                                     row.get("Registration_Link")) if x),
            categories=[str(c).strip() for c in cats if str(c).strip()],
            venue_name=(row.get("Venue_Name") or "").strip() or None,
            venue_address=", ".join(x for x in ((row.get("Venue_Address") or "").strip(), "Jersey City, NJ",
                                                (row.get("Venue_Zip") or "").strip()) if x),
            organizer_name=(row.get("Org_Name") or "").strip() or None,
            start_utc=start, end_utc=when(row["Event_Date"], row.get("End_Time")),
            date=start.astimezone(TZ).date().isoformat(),
        ))
    return raws
