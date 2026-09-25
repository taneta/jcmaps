"""Compose the snapshot the site reads and the run report; carry a failed or shrunken source's last good events."""
from __future__ import annotations

from datetime import datetime, timedelta

from pipeline.model import Event, Occurrence, Raw, Snapshot, Venue
from pipeline.util import ROOT

SITE_DATA = ROOT / "site" / "data"
SNAPSHOT = SITE_DATA / "events.json"
REPORT = SITE_DATA / "report.json"  # the latest report, published with the site
REPORTS = ROOT / "reports"  # one file per run, uploaded as a workflow artifact, never committed
VOLATILE = {"first_seen", "last_seen", "updated_at"}
CARRY = timedelta(hours=24)  # how long after its last successful fetch a failed or shrunken source keeps its events
SHRINK = 0.30  # a feed listing this much fewer events than the source published is judged like a failed fetch
MIN_BASE = 10  # unless the source published too few to judge


def shrank(previous: dict, sid: str, fresh: int) -> str | None:
    """Why a source whose fetch worked is still judged like a failed one: its feed lists far fewer events than the
    source published last time. A feed that quietly broke looks like this, and so does a real drop; both are carried
    for a day (see carry), then the smaller feed is published, which settles the comparison."""
    before = previous.get("sources", {}).get(sid, {}).get("count", 0)
    if before >= MIN_BASE and fresh < before * (1 - SHRINK):
        return f"shrank from {before} to {fresh}"
    return None


def carry(previous: dict, failed: set[str],
          now: datetime) -> tuple[dict[str, str], list[Raw], dict[str, dict], dict[str, Venue]]:
    """A source whose fetch failed or shrank keeps its last good events until CARRY after its last successful fetch.
    Returns when that fetch was, per carried source, and its events from the previous snapshot as records with the
    fields and venues they were published with, so the checks and the gate judge them like fresh ones. The records
    carry no evidence, so a fresh listing of the same event wins the duplicate check. The events are read through
    the Event model, so a field added since that snapshot takes its default."""
    since: dict[str, str] = {}
    for sid in failed:
        src = previous.get("sources", {}).get(sid)
        fetched = src and src.get("carried_from", previous["generated_at"])
        if fetched and now - datetime.fromisoformat(fetched) <= CARRY:
            since[sid] = fetched
    events = {e["id"]: Event(**e).model_dump() for e in previous.get("events", []) if e["source_id"] in since}
    raws = [Raw(source_id=e["source_id"], source_uid=e["source_uid"], title=e["title"], url=e["url"],
                organizer_name=e["organizer_name"], alt_urls=e["alt_urls"], venue_id=o["venue_id"],
                start_utc=o["start_utc"], end_utc=o["end_utc"], all_day=o["all_day"], date=o["date"])
            for o in previous.get("occurrences", []) if (e := events.get(o["event_id"]))]
    used = {r.venue_id for r in raws}
    return since, raws, events, {v["id"]: Venue(**v) for v in previous.get("venues", []) if v["id"] in used}


def compose(raws: list[Raw], fields: dict[str, dict], venues: dict[str, Venue], city: dict,
            now: datetime, previous: dict | None, carried: dict[str, str] | None = None) -> Snapshot:
    """carried: source id -> when the events carried forward for it were fetched (see carry)."""
    carried = carried or {}
    ts = now.isoformat(timespec="seconds")
    prev = {e["id"]: e for e in (previous or {}).get("events", [])}
    events: list[Event] = []
    occurrences: list[Occurrence] = []
    for r in raws:
        f = fields[r.id]
        span = (r.end_utc - r.start_utc) if r.end_utc else timedelta(0)
        ev = Event(
            id=r.id, source_id=r.source_id, source_uid=r.source_uid, title=r.title, url=r.url,
            organizer_name=r.organizer_name, organizer_type=f["organizer_type"], topics=f["topics"], type=f["type"],
            kid_friendly=f["kid_friendly"], age_min=f["age_min"], age_max=f["age_max"], age_text=f["age_text"],
            price=f["price"], price_text=f["price_text"], registration=f["registration"], summary=f["summary"],
            ongoing=span > timedelta(hours=24) and not (r.all_day and span <= timedelta(days=1)),
            status=f["status"], evidence=f["evidence"], alt_urls=r.alt_urls,
            first_seen=ts, last_seen=ts, updated_at=ts,
        )
        old = prev.get(r.id)
        if old:
            ev.first_seen = old.get("first_seen", ts)
            if r.source_id in carried:
                ev.last_seen = old["last_seen"]  # not in its feed this run
            same = ev.model_dump(exclude=VOLATILE) == {k: v for k, v in old.items() if k not in VOLATILE}
            ev.updated_at = old.get("updated_at", ts) if same else ts
        events.append(ev)
        occurrences.append(Occurrence(event_id=r.id, venue_id=r.venue_id, start_utc=r.start_utc, end_utc=r.end_utc,
                                      all_day=r.all_day, date=r.date, tz=city["tz"]))
    used = {o.venue_id for o in occurrences}
    counts: dict[str, dict] = {}
    for e in events:
        counts.setdefault(e.source_id, {"count": 0})["count"] += 1
    for sid, fetched in carried.items():
        if sid in counts:
            counts[sid]["carried_from"] = fetched
    return Snapshot(generated_at=ts, city={k: city[k] for k in ("name", "tz", "center", "bbox")},
                    sources=counts, venues=[v for v in venues.values() if v.id in used],
                    events=events, occurrences=occurrences)


def report(now: datetime, sources: dict, drops: list[dict], venues: dict[str, Venue], geocode_calls: int,
           enrich_stats: dict, gate_reasons: list[str], published: int, duration_s: float) -> dict:
    by_reason: dict[str, int] = {}
    for d in drops:
        by_reason[d["reason"]] = by_reason.get(d["reason"], 0) + 1
    return {
        "run_at": now.isoformat(timespec="seconds"),
        "sources": sources,
        "published": published,
        "drops": by_reason,
        "drop_examples": [d for d in drops if d["reason"] not in ("past", "beyond_horizon")][:40],
        "geocode": {"venues": len(venues), "with_coords": sum(1 for v in venues.values() if v.lat is not None),
                    "calls": geocode_calls,
                    "failed": [v.name for v in venues.values() if v.lat is None][:40]},
        "enrich": enrich_stats,
        "gate": {"passed": not gate_reasons, "reasons": gate_reasons},
        "duration_s": round(duration_s, 1),
    }
