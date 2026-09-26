"""jcmaps build: fetch, parse, enrich, geocode, check, publish. jcmaps eval-enrich: the hand-check table.
jcmaps score-enrich: the current prompt and model against the labeled set."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

from pipeline import check, enrich, gate, llm, publish
from pipeline.geocode import Geocoder, build_venues, nominatim_query
from pipeline.model import Raw
from pipeline.sources import ical, library, moderncampus, njdoh, tribe
from pipeline.util import ROOT, UA, env, normalize, now_utc, read_json, spaced, write_json

CITY = ROOT / "city.json"
BRANCHES = ROOT / "data" / "library_branches.json"
FIXTURES = ROOT / "fixtures"
CACHE = ROOT / "cache"
PULLED = ("events.json", "enrich.json", "geocode.json")
# Sources read from one URL into one file, by kind: any module with fetch(sid, url, cache_dir, client) and parse(text, src).
SINGLE = {"ical": (ical, "ics"), "njdoh": (njdoh, "csv"), "moderncampus": (moderncampus, "json")}


def pull(site_url: str, client: httpx.Client) -> dict[str, str]:
    """Fetch the previous deployment's snapshot and caches into site/data. The live site is the state between runs;
    a miss only means a cold start (full enrichment and geocoding), never lost data."""
    got: dict[str, str] = {}
    for name in PULLED:
        url = site_url.rstrip("/") + "/data/" + name
        try:
            r = client.get(url)
            if r.status_code == 200:
                json.loads(r.text)
                publish.SITE_DATA.mkdir(parents=True, exist_ok=True)
                (publish.SITE_DATA / name).write_text(r.text)
                got[name] = f"{len(r.content)} bytes"
            else:
                got[name] = f"HTTP {r.status_code}"
        except (httpx.HTTPError, ValueError) as e:
            got[name] = type(e).__name__
    return got


def load_raws(city: dict, only: str | None, root: Path | None, client: httpx.Client | None) -> tuple[list[Raw], dict]:
    """root: read the feeds saved there instead of fetching (FIXTURES, the frozen ones; CACHE, the last fetched)."""
    raws: list[Raw] = []
    stats: dict[str, dict] = {}
    branches = read_json(BRANCHES, {}) or {}
    for src in city["sources"]:
        sid = src["id"]
        if not src.get("publish") or (only and sid != only):
            continue
        try:
            got: list[Raw] = []
            if src["kind"] == "ics":
                for cid in src["calendars"]:
                    if root == FIXTURES and not (root / "library" / f"{cid}.ics").exists():
                        continue  # only a few calendars are frozen
                    text = ((root / "library" / f"{cid}.ics").read_text() if root
                            else library.fetch(cid, CACHE / "library", client))
                    got += library.parse(text, cid, branches.get(cid))
            elif src["kind"] in SINGLE:
                mod, ext = SINGLE[src["kind"]]
                text = ((root / src["kind"] / f"{sid}.{ext}").read_text() if root
                        else mod.fetch(sid, src["url"], CACHE / src["kind"], client))
                got += mod.parse(text, src)
            else:
                pages = ([json.loads(p.read_text()) for p in sorted((root / "tribe").glob(f"{sid}.p*.json"))]
                         if root else tribe.fetch(sid, src["url"], CACHE / "tribe", client))
                if root and not pages:
                    raise FileNotFoundError(root / "tribe" / f"{sid}.p1.json")
                got += tribe.parse(pages, sid, src["organizer_type"])
            # a venue's copy of another organizer's event, when that organizer's own site disagrees (docs/sources.md)
            skip = re.compile(src["skip"], re.I) if src.get("skip") else None
            kept = [r for r in got if not (skip and skip.search(r.title))]
            # a countywide calendar (require_venue): an event with no place named is not the city's to show
            placed = [r for r in kept if r.venue_address or not src.get("require_venue")]
            stats[sid] = {"parsed": len(placed), **({"skipped": len(got) - len(kept)} if skip else {}),
                          **({"no_venue": len(kept) - len(placed)} if src.get("require_venue") else {})}
            raws += placed
        except Exception as e:  # a broken source yields no fresh events; build carries its last good ones
            stats[sid] = {"parsed": 0, "error": f"could not be fetched ({type(e).__name__}: {str(e)[:200]})"}
            print(f"source {sid} failed: {e}", file=sys.stderr)
    return raws, stats


def build(only: str | None, offline: bool, no_model: bool, pull_from: str | None, cached: bool = False) -> int:
    t0 = time.monotonic()
    now = now_utc()
    city = json.loads(CITY.read_text())
    client = httpx.Client(headers={"User-Agent": UA}, timeout=60, follow_redirects=True,
                          event_hooks={"request": [spaced(city.get("crawl_delay_s", {}))]})
    pulled = pull(pull_from, client) if pull_from else {}

    raws, src_stats = load_raws(city, only, FIXTURES if offline else CACHE if cached else None, client)
    raws, drops = check.prefilter(raws, now)
    # a partial or fixture build must not be judged against the full snapshot, nor carry from it
    previous = None if (only or offline) else read_json(publish.SNAPSHOT)
    fresh = Counter(r.source_id for r in raws)
    for sid, s in src_stats.items():  # a feed that lists far fewer events than last time is judged like a failed fetch
        if "error" not in s and (why := publish.shrank(previous or {}, sid, fresh[sid])):
            s["error"] = why
    failed = {sid for sid, s in src_stats.items() if "error" in s}
    since, old, old_fields, old_venues = publish.carry(previous or {}, failed, now)
    raws = [r for r in raws if r.source_id not in since]  # a carried source's smaller feed waits its day out
    old, _ = check.prefilter(old, now)  # carried occurrences that are over are not reused

    model_client = None if (offline or no_model) else llm.make_client()
    classify = (lambda text: llm.classify(model_client, text)) if model_client else None
    cap = float(env("JCMAP_COST_CAP_USD", "5"))
    fields, enrich_stats = enrich.enrich_all(raws, classify, cap, concurrency=int(env("JCMAP_CONCURRENCY", "6")),
                                             organizer_defaults={s["id"]: s.get("organizer_type", "unknown") for s in city["sources"]})
    enrich_stats["model"] = llm.MODEL if classify else None
    for r in raws:  # offsite events get their venue from the model, with a quote
        f = fields[r.id]
        if r.offsite and f["venue_address"]:
            r.venue_name, r.venue_address = f["venue_name"], f["venue_address"]

    geocoder = Geocoder(None if offline else nominatim_query(client, city["bbox"]))
    venues = {**old_venues, **build_venues(raws, geocoder)}
    raws, drops2 = check.check(raws + old, venues, city["boundary"])  # fresh records first, so they win duplicates
    drops += drops2
    unpinned = Counter(venues[r.venue_id].name for r in raws if r.venue_id and venues[r.venue_id].lat is None)

    snapshot = publish.compose(raws, fields | old_fields, venues, city, now, previous, since)
    reasons = gate.gate(snapshot, city["boundary"], now)
    candidate = json.dumps(snapshot.model_dump(mode="json", by_alias=True), ensure_ascii=False, default=str)
    public = {str(f.relative_to(ROOT)): f.read_text(errors="replace")
              for f in (ROOT / "site").rglob("*") if f.is_file() and f != publish.SNAPSHOT and "node_modules" not in f.parts}
    reasons += gate.secret_scan({"candidate events.json": candidate, **public})
    for sid, s in src_stats.items():  # degraded while its last good events are carried, down with nothing to show
        s["published"] = snapshot.sources.get(sid, {}).get("count", 0)
        s["state"] = "degraded" if sid in since else "down" if sid in failed and not s["published"] else "active"
        if sid in since:
            s["carried_from"] = since[sid]

    rep = publish.report(now, src_stats, drops, venues, dict(unpinned.most_common(40)), geocoder.calls, enrich_stats,
                         reasons, len(snapshot.events), time.monotonic() - t0)
    rep["pulled"] = pulled
    stamp = now.strftime("%Y-%m-%dT%H%M")
    write_json(publish.REPORTS / f"{stamp}.json", rep)
    write_json(publish.REPORT, rep)
    print(json.dumps({k: rep[k] for k in ("sources", "published", "drops", "geocode", "enrich", "gate", "duration_s")},
                     indent=1, default=str))
    if reasons:
        print("GATE FAILED; last good snapshot kept:", "; ".join(reasons), file=sys.stderr)
        return 2
    publish.SNAPSHOT.write_text(candidate + "\n")
    return 0


def eval_enrich(n: int = 30) -> int:
    """Print n enriched events with their quotes for a hand-check and write the labeled-set candidate."""
    snap = read_json(publish.SNAPSHOT)
    if not snap:
        print("no snapshot; run jcmaps build first", file=sys.stderr)
        return 1
    by_source: dict[str, list[dict]] = {}
    for e in snap["events"]:
        by_source.setdefault(e["source_id"], []).append(e)
    picked: list[dict] = []
    titles: set[str] = set()
    while len(picked) < n and any(by_source.values()):
        for evs in by_source.values():
            while evs and len(picked) < n:  # one event per title, so recurring programs do not crowd the set
                e = evs.pop(len(evs) // 2)
                if e["title"] not in titles:
                    titles.add(e["title"])
                    picked.append(e)
                    break
    cache = read_json(enrich.CACHE, {}) or {}
    inputs = {}
    root = CACHE if (CACHE / "library").exists() else FIXTURES  # the last fetched feeds, or the frozen ones
    for src in [s for s in json.loads(CITY.read_text())["sources"] if s.get("publish")]:
        for raw in load_raws({"sources": [src]}, None, root, None)[0]:
            inputs[raw.id] = raw.enrich_text()
    rows = []
    for e in picked:
        q = {k: v["quote"] for k, v in e["evidence"].items() if v["from"] == "model"}
        print(f"\n[{e['id']}] {e['title']}\n  kid={e['kid_friendly']} ({q.get('kid_friendly', '-')}) | price={e['price']}"
              f" ({q.get('price', '-')}) | reg={e['registration']} ({q.get('registration', '-')}) | org={e['organizer_type']}"
              f" ({q.get('organizer_type', '-')}) | ages={e['age_text']} | status={e['status']}\n  summary: {e['summary']}\n  {e['url']}")
        rows.append({"id": e["id"], "title": e["title"], "url": e["url"], "input": inputs.get(e["id"]),
                     "expected": {k: e[k] for k in ("kid_friendly", "price", "registration", "organizer_type", "status", "age_text")},
                     "quotes": q, "summary": e["summary"]})
    write_json(ROOT / "fixtures" / "labeled" / "enrich.candidate.json", rows)
    print(f"\n{len(rows)} events written to fixtures/labeled/enrich.candidate.json; correct it and rename to enrich.json")
    return 0


def score_enrich(classify: Callable[[str], llm.Call]) -> dict:
    """Run the model on the labeled set and print how often each field agrees with the label, the misses and the
    cost. Only fields the model decided count: a label without a model quote came from an adapter rule."""
    rows = json.loads((FIXTURES / "labeled" / "enrich.json").read_text())
    with ThreadPoolExecutor(6) as pool:
        calls = list(pool.map(lambda r: classify(r["input"]), rows))
    blank = {"kid_friendly": "unknown", "price": "unknown", "registration": "unknown", "organizer_type": "unknown",
             "status": "scheduled", "age_text": None}
    agree, seen, misses = Counter(), Counter(), []
    for row, call in zip(rows, calls):
        got = {k: v for k, (v, _) in enrich.proved(call.out or {}, normalize(row["input"])).items()}
        for field, default in blank.items():
            expected = row["expected"][field]
            if expected != default and ("age" if field == "age_text" else field) not in row["quotes"]:
                continue  # an adapter rule decided it
            seen[field] += 1
            if normalize(str(got.get(field, default))) == normalize(str(expected)):
                agree[field] += 1
            else:
                misses.append(f"{row['id']} {field}: expected {expected!r}, got {got.get(field, default)!r}")
    cost = round(sum(c.cost_usd for c in calls), 4)
    for field in blank:
        print(f"{field:15} {agree[field]}/{seen[field]}")
    print("\n".join(misses) or "no misses")
    print(f"{len(calls)} calls, ${cost} ({llm.MODEL})")
    return {"agree": dict(agree), "seen": dict(seen), "misses": misses, "cost_usd": cost}


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="jcmaps")
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--source")
    b.add_argument("--offline", action="store_true", help="fixtures instead of feeds; no geocoding or model calls")
    b.add_argument("--no-model", action="store_true")
    b.add_argument("--cached", action="store_true",
                   help="the feeds the last fetching run left in cache/ instead of fetching; how a push to main builds")
    b.add_argument("--pull", nargs="?", const="", metavar="URL",
                   help="first fetch the previous snapshot and caches from the live site (default: site_url in city.json)")
    sub.add_parser("eval-enrich")
    sub.add_parser("score-enrich")
    a = p.parse_args(argv)
    if a.cmd == "build":
        site_url = None
        if a.pull is not None:
            site_url = a.pull or json.loads(CITY.read_text()).get("site_url")
            if not site_url:
                p.error("--pull needs a URL or site_url in city.json")
        sys.exit(build(a.source, a.offline, a.no_model, site_url, a.cached))
    if a.cmd == "score-enrich":
        client = llm.make_client()
        if not client:
            p.error("score-enrich needs OPENAI_API_KEY (in .env locally)")
        score_enrich(lambda text: llm.classify(client, text))
        sys.exit(0)
    sys.exit(eval_enrich())


if __name__ == "__main__":
    main()
