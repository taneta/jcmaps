"""Enrichment: adapter rules first, then one model call per new or changed event.
A model-filled value survives only if its quote is a substring of the normalized input; otherwise unknown."""
from __future__ import annotations

import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from pipeline.check import status_of
from pipeline.model import Evidence, EventType, Raw
from pipeline.sources.library import MONEY
from datetime import timedelta

from pipeline.util import ROOT, normalize, now_utc, read_json, sha, write_json

CACHE = ROOT / "site" / "data" / "enrich.json"  # published with the site, pulled back on the next run
KEEP_DAYS = 60  # cache entries not used for this long are dropped

# An event's type, for its icon on the map and in the list (docs/design.md, Icons). Code decides, never the model:
# the first type whose words are in the title, else the first of the feed's own categories that names one; the
# matched words are the evidence. No match means unknown, a plain pin. The order settles overlaps: a festival with a
# band is a festival, musical bingo is a game.
TITLE_WORDS: list[tuple[EventType, str]] = [
    ("festivals", r"festival|\bfest\b|oktoberfest|\bparades?\b|block party|street fair|carnival|fiesta|tree lighting"),
    ("markets", r"\bmarkets?\b|\bfairs?\b|flea|bazaar|\bswap\b|\bsale\b|food crawl"),
    ("stories", r"storytime|story ?time|story ?hour|\bstor(?:y|ies)\b|cuentos|\bbooks?\b|\bread(?:ing|s)?\b|read-aloud|lectura"
                r"|author|\bpoe(?:m|ms|try|t|ts)\b|\bwrit(?:e|ing|ers?)\b|bookmobile|literary"),
    ("games", r"\bgames?\b|bingo|chess|trivia|\blegos?\b|minecraft|pok[eé]mon|dungeons|d&d|puzzle|escape room|gaming"),
    ("shows", r"theat(?:er|re)|\bmusical\b|puppet|cabaret|comedy|stand-up|improv|magic show|\bmovies?\b|\bfilms?\b|cinema"
              r"|matinee|circus|opera|drag show"),
    ("music", r"\bmusic\b|concert|\bband\b|jazz|choir|orchestra|symphony|\bdj\b|karaoke|karoke|vinyl|open mic|\bsing(?:ing)?\b"
              r"|salsa|flamenco|bachata|\bdanc(?:e|es|ing)\b|ballet|hip.hop|boogie|groove|unplugged|silent stage|sextet|quartet"),
    ("health", r"yoga|pilates|zumba|fitness|workout|exercise|run club|\brun(?:ning)?\b|\bwalk(?:ing)?\b|\bhik(?:e|ing)\b|cycling"
               r"|\bbik(?:e|ing)\b|soccer|basketball|baseball|tennis|swim|\bsports?\b|martial arts|karate|self.defen[cs]e|\bhealth"
               r"|wellness|vaccin|medical|dental|blood drive|medicare|menopause|meditation|mindful|tai chi"),
    ("crafts", r"craft|\barts?\b|artist|creativ|\bpaint|\bdraw(?:ing)?\b|sketch|\bsew|knit|crochet|\bclay\b|pottery|ceramic"
               r"|jewel|\bbead|bracelet|mosaic|collage|origami|felting|\btote\b|coloring|\bmak(?:ing|ers?|ery|erspace)\b"
               r"|3d print|silk screen|keychain|bookmark|exhibit|gallery|studio|upcycl|sneakers|trinket|photo|junk journal|scrapbook"),
    ("classes", r"\bclass(?:es)?\b|workshop|\blessons?\b|course|training|seminar|lecture|\btalks?\b|info(?:rmation)? session"
                r"|open house|\bq&a\b|panel|discussion|conversation|\blearn|language|spanish|english|\besl\b|hindi|japanese"
                r"|french|mandarin|\basl\b|sign language|tutor|homework|(?-i:\bSAT\b)|test prep|r[eé]sum[eé]|\bjobs?\b|career"
                r"|business|financ|money|\btech\b|computer|coding|3d model|podcast|etiquette|admission|college|preparedness"
                r"|history|\b101\b|intro(?:duction)? to"),
    ("meetups", r"mixer|speed dating|singles|happy hour|meet ?-?up|networking|social club|club meeting|date night|couples"
                r"|volunteer|clean ?-?up|hangout"),
]
CATEGORY_WORDS: list[tuple[EventType, str]] = [
    ("festivals", r"festival"), ("markets", r"market"), ("stories", r"storytime|literary|author|literature"),
    ("games", r"games"), ("shows", r"\bfilm|moving image|theat"), ("music", r"music|dance"),
    ("health", r"health|wellness|sport|fitness"), ("crafts", r"crafts|visual arts|exhibition|makerspace|photography"),
    ("classes", r"educational|workshop|computer|s\.?t\.?e\.?a?\.?m|training"), ("meetups", r"social gatherings"),
]
_TITLE = [(t, re.compile(rx, re.I)) for t, rx in TITLE_WORDS]
_CATEGORY = [(t, re.compile(rx, re.I)) for t, rx in CATEGORY_WORDS]
FREE_TO_ENTER = re.compile(r"farmers?['’]?\s+market|street fair", re.I)
FREE_TO_ENTER_SOURCES = {"culture"}  # the city's own calendar (Office of Cultural Affairs)


def type_of(raw: Raw) -> tuple[EventType, Evidence | None]:
    for t, rx in _TITLE:
        if m := rx.search(raw.title):
            return t, Evidence(quote=m.group(0), from_="title")
    for category in raw.categories:  # in the feed's order; the library writes "Popular Events > Storytime Events"
        short = category.split(">")[-1].strip()
        for t, rx in _CATEGORY:
            if rx.search(short):
                return t, Evidence(quote=short, from_="categories")
    return "unknown", None


def quoted(quote: str | None, norm_text: str) -> bool:
    return bool(quote) and 3 <= len(quote) <= 300 and normalize(quote) in norm_text


def proved(out: dict, norm: str) -> dict[str, tuple[str, str]]:
    """The model's answers that pass the evidence rule, as field: (value, quote). An answer it marked unknown, or
    whose quote is not in the normalized input, is left out. Shared by merge and by `jcmaps score-enrich`."""
    p: dict[str, tuple[str, str]] = {}
    for field in ("kid_friendly", "price", "registration", "organizer_type"):
        if out.get(field) not in (None, "unknown") and quoted(out.get(f"{field}_quote"), norm):
            p[field] = (out[field], out[f"{field}_quote"])
    if out.get("status") == "cancelled" and quoted(out.get("status_quote"), norm):
        p["status"] = ("cancelled", out["status_quote"])
    if quoted(out.get("age_text"), norm):
        p["age_text"] = (out["age_text"], out["age_text"])
    return p


def merge(raw: Raw, out: dict | None, organizer_default: str = "unknown") -> dict:
    """Event fields from the adapter's rules plus whatever the model proved with a quote.
    organizer_default is the source's kind (city, community) and applies only when nothing else decided."""
    kind, why = type_of(raw)
    f: dict = {
        "kid_friendly": raw.kid_friendly, "price": raw.price, "organizer_type": raw.organizer_type,
        "status": status_of(raw), "topics": list(raw.topics), "type": kind,
        "evidence": dict(raw.evidence) | ({"type": why} if why else {}),
        "age_min": None, "age_max": None, "age_text": None, "price_text": raw.cost_text,
        "registration": "unknown", "summary": None, "venue_name": None, "venue_address": None,
    }
    if not out:
        return _fallback(f, raw, organizer_default)
    norm = normalize(raw.enrich_text())
    for field, (value, quote) in proved(out, norm).items():
        if field == "age_text":
            f["age_text"], f["age_min"], f["age_max"] = value, out.get("age_min"), out.get("age_max")
            f["evidence"]["age"] = Evidence(quote=quote, from_="model")
        elif f[field] in ("unknown", "scheduled"):  # an adapter rule's answer stands; the model fills the rest
            f[field] = value
            f["evidence"][field] = Evidence(quote=quote, from_="model")
    if quoted(out.get("price_text"), norm):
        f["price_text"] = out["price_text"]
    if out.get("summary"):
        f["summary"] = out["summary"].strip()[:200]
    f["topics"] = sorted(set(f["topics"]) | {t for t in out.get("topics") or [] if isinstance(t, str)})
    if (out.get("venue_name") or out.get("venue_address")) and quoted(out.get("venue_quote"), norm):
        # an offsite listing takes it as its venue; any other keeps it as a hint for a venue the address could not place
        f["venue_name"], f["venue_address"] = out.get("venue_name") or out["venue_address"], out.get("venue_address")
        f["evidence"]["venue"] = Evidence(quote=out["venue_quote"], from_="model")
    return _fallback(f, raw, organizer_default)


def _fallback(f: dict, raw: Raw, organizer_default: str) -> dict:
    if f["organizer_type"] == "unknown" and organizer_default != "unknown":
        f["organizer_type"] = organizer_default
        f["evidence"]["organizer_type"] = Evidence(quote=f"source: {raw.source_id}", from_="rule")
    # Farmers markets and street fairs on the city's calendar are free to enter: the owner's rule, like the library's
    # "library program" (#16). It decides only what nothing else did, and never for a listing that talks about money;
    # the title words are the evidence.
    if (f["price"] == "unknown" and raw.source_id in FREE_TO_ENTER_SOURCES and (m := FREE_TO_ENTER.search(raw.title))
            and not MONEY.search(f"{raw.title}\n{raw.description}")):
        f["price"] = "free"
        f["evidence"]["price"] = Evidence(quote=m.group(0), from_="rule")
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
