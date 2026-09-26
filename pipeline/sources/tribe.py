"""The Events Calendar (WordPress) REST API, shared by the two city sites."""
from __future__ import annotations

import html
import json
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

import httpx

from pipeline.model import Evidence, Raw
from pipeline.util import TZ, scrub, strip_html

API = "{base}/wp-json/tribe/events/v1/events?per_page=50&page={page}&start_date=now"
MAX_PAGES = 20


def fetch(source_id: str, base: str, cache_dir: Path, client: httpx.Client) -> list[dict]:
    pages: list[dict] = []
    cache_dir.mkdir(parents=True, exist_ok=True)
    for page in range(1, MAX_PAGES + 1):
        r = client.get(API.format(base=base, page=page))
        r.raise_for_status()
        text = scrub(r.text)
        (cache_dir / f"{source_id}.p{page}.json").write_text(text)
        data = json.loads(text)
        pages.append(data)
        if not data.get("next_rest_url"):
            break
    return pages


def _local(wall: str, all_day: bool, end: bool) -> datetime:
    """Wall-clock strings are local time whatever the site's timezone field says
    (Jersey City Connects reports UTC+0 while its times are clearly local)."""
    dt = datetime.strptime(wall, "%Y-%m-%d %H:%M:%S")
    if all_day:
        dt = datetime.combine(dt.date() + (timedelta(days=1) if end else timedelta()), time(0))
    return dt.replace(tzinfo=TZ).astimezone(timezone.utc)


def _price(cost: str) -> tuple[str, Evidence | None]:
    c = cost.strip()
    if not c:
        return "unknown", None
    if c.lower() in {"free", "0", "$0", "$0.00"} or "free" in c.lower():
        return "free", Evidence(quote=c.lower(), from_="cost")
    return "paid", Evidence(quote=c.lower(), from_="cost")


def parse(pages: list[dict], source_id: str, organizer_type: str = "unknown") -> list[Raw]:
    """organizer_type is kept for the call signature; the source default is applied after enrichment."""
    raws: list[Raw] = []
    for page in pages:
        for e in page.get("events", []):
            if e.get("status") not in (None, "publish") or e.get("hide_from_listings"):
                continue
            venue = e.get("venue") if isinstance(e.get("venue"), dict) else {}
            all_day = bool(e.get("all_day"))
            start = _local(e["start_date"], all_day, end=False)
            end = _local(e["end_date"], all_day, end=True) if e.get("end_date") else None
            cost = html.unescape(e.get("cost") or "")
            price, ev = _price(cost)
            evidence: dict[str, Evidence] = {}
            if ev:
                evidence["price"] = ev
            cats = [html.unescape(c.get("name", "")) for c in e.get("categories", [])]
            kid = "unknown"
            if any("kid" in c.lower() or "child" in c.lower() or "family" in c.lower() for c in cats):
                kid = "yes"
                evidence["kid_friendly"] = Evidence(
                    quote=next(c for c in cats if any(k in c.lower() for k in ("kid", "child", "family"))).lower(),
                    from_="categories")
            address = ", ".join(x for x in (venue.get("address"), venue.get("city"), venue.get("zip")) if x)
            organizers = [html.unescape(o.get("organizer", "")) for o in (e.get("organizer") or []) if isinstance(o, dict)]
            raws.append(Raw(
                source_id=source_id, source_uid=str(e["id"]), title=html.unescape(e.get("title", "")).strip(),
                url=e.get("url", ""), description=strip_html(e.get("description") or ""), categories=cats,
                cost_text=cost or None, venue_name=html.unescape(venue.get("venue") or "") or None,
                venue_address=address or None, organizer_name=", ".join(o for o in organizers if o) or None,
                start_utc=start, end_utc=end, all_day=all_day, date=start.astimezone(TZ).date().isoformat(),
                kid_friendly=kid, price=price, organizer_type="unknown",
                topics=sorted({c for c in cats if c and c != "What's Coming Up?"}), evidence=evidence,
            ))
    return raws
