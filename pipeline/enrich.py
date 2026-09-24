"""Enrichment: adapter rules first, then one model call per new or changed event.
A model-filled value survives only if its quote is a substring of the normalized input; otherwise unknown."""
from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from pipeline.check import status_of
from pipeline.model import Evidence, Raw
from datetime import timedelta

from pipeline.util import ROOT, normalize, now_utc, read_json, sha, write_json

CACHE = ROOT / "site" / "data" / "enrich.json"  # published with the site, pulled back on the next run
KEEP_DAYS = 60  # cache entries not used for this long are dropped


def quoted(quote: str | None, norm_text: str) -> bool:
    return bool(quote) and 3 <= len(quote) <= 300 and normalize(quote) in norm_text


def merge(raw: Raw, out: dict | None, organizer_default: str = "unknown") -> dict:
    """Event fields from the adapter's rules plus whatever the model proved with a quote.
    organizer_default is the source's kind (city, community) and applies only when nothing else decided."""
    f: dict = {
        "kid_friendly": raw.kid_friendly, "price": raw.price, "organizer_type": raw.organizer_type,
        "status": status_of(raw), "topics": list(raw.topics), "evidence": dict(raw.evidence),
        "age_min": None, "age_max": None, "age_text": None, "price_text": raw.cost_text,
        "registration": "unknown", "summary": None, "venue_name": None, "venue_address": None,
    }
    if not out:
        return _fallback(f, raw, organizer_default)
    norm = normalize(raw.enrich_text())

    def take(field: str, value, quote):
        if f[field] != "unknown" or value in (None, "unknown"):
            return  # an adapter rule already decided, or the model had nothing
        if quoted(quote, norm):
            f[field] = value
            f["evidence"][field] = Evidence(quote=quote, from_="model")

    take("kid_friendly", out.get("kid_friendly"), out.get("kid_friendly_quote"))
    take("price", out.get("price"), out.get("price_quote"))
    take("registration", out.get("registration"), out.get("registration_quote"))
    take("organizer_type", out.get("organizer_type"), out.get("organizer_type_quote"))
    if f["status"] == "scheduled" and out.get("status") == "cancelled" and quoted(out.get("status_quote"), norm):
        f["status"] = "cancelled"
        f["evidence"]["status"] = Evidence(quote=out["status_quote"], from_="model")
    if quoted(out.get("age_text"), norm):
        f["age_text"], f["age_min"], f["age_max"] = out["age_text"], out.get("age_min"), out.get("age_max")
        f["evidence"]["age"] = Evidence(quote=out["age_text"], from_="model")
    if quoted(out.get("price_text"), norm):
        f["price_text"] = out["price_text"]
    if out.get("summary"):
        f["summary"] = out["summary"].strip()[:200]
    f["topics"] = sorted(set(f["topics"]) | {t for t in out.get("topics") or [] if isinstance(t, str)})
    if raw.offsite and out.get("venue_address") and quoted(out.get("venue_quote"), norm):
        f["venue_name"], f["venue_address"] = out.get("venue_name") or out["venue_address"], out["venue_address"]
        f["evidence"]["venue"] = Evidence(quote=out["venue_quote"], from_="model")
    return _fallback(f, raw, organizer_default)


def _fallback(f: dict, raw: Raw, organizer_default: str) -> dict:
    if f["organizer_type"] == "unknown" and organizer_default != "unknown":
        f["organizer_type"] = organizer_default
        f["evidence"]["organizer_type"] = Evidence(quote=f"source: {raw.source_id}", from_="rule")
    return f


def enrich_all(raws: list[Raw], classify: Callable[[str], object] | None, cap_usd: float,
               cache_path=CACHE, concurrency: int = 1, organizer_defaults: dict[str, str] | None = None) -> tuple[dict[str, dict], dict]:
    """classify(text) -> llm.Call, or None when no model is available. Returns fields per event id and stats.
    Calls run in chunks of `concurrency`; the cost cap is checked between chunks."""
    cache = read_json(cache_path, {}) or {}
    stats = {"calls": 0, "cached": 0, "no_model": 0, "errors": 0, "cost_usd": 0.0, "stopped_at_cap": False, "pruned": 0}
    today = now_utc().date().isoformat()
    texts = {r.id: r.enrich_text() for r in raws}
    todo = []
    for r in raws:
        h = sha(texts[r.id])
        if h in cache:
            stats["cached"] += 1
            cache[h]["seen"] = today
        elif classify is not None:
            todo.append((h, texts[r.id]))
    seen: set[str] = set()
    todo = [t for t in todo if not (t[0] in seen or seen.add(t[0]))]
    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        for i in range(0, len(todo), max(1, concurrency)):
            if stats["stopped_at_cap"]:
                break
            chunk = todo[i:i + max(1, concurrency)]
            for (h, _), call in zip(chunk, pool.map(lambda t: classify(t[1]), chunk)):
                stats["calls"] += 1
                stats["cost_usd"] = round(stats["cost_usd"] + call.cost_usd, 6)
                if call.error:
                    stats["errors"] += 1
                else:
                    cache[h] = {"out": call.out, "model": call.model, "at": now_utc().isoformat(timespec="seconds"), "seen": today}
            write_json(cache_path, cache, compact=True)
            if stats["cost_usd"] >= cap_usd:
                stats["stopped_at_cap"] = True
    cutoff = (now_utc().date() - timedelta(days=KEEP_DAYS)).isoformat()
    stale = [h for h, e in cache.items() if (e.get("seen") or e.get("at", ""))[:10] < cutoff]
    for h in stale:
        del cache[h]
    stats["pruned"] = len(stale)
    if stale or todo:
        write_json(cache_path, cache, compact=True)
    fields: dict[str, dict] = {}
    for r in raws:
        entry = cache.get(sha(texts[r.id]))
        if entry is None and (classify is None or stats["stopped_at_cap"]):
            stats["no_model"] += 1
        fields[r.id] = merge(r, entry["out"] if entry else None, (organizer_defaults or {}).get(r.source_id, "unknown"))
    return fields, stats
