"""jcmaps build: fetch, parse, enrich, geocode, check, publish. jcmaps eval-enrich: the hand-check table."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import httpx

from pipeline import check, enrich, gate, llm, publish
from pipeline.geocode import Geocoder, build_venues, nominatim_query
from pipeline.model import Raw
from pipeline.sources import library, tribe
from pipeline.util import ROOT, UA, env, now_utc, read_json, write_json

CITY = ROOT / "city.json"
BRANCHES = ROOT / "data" / "library_branches.json"
FIXTURES = ROOT / "fixtures"
CACHE = ROOT / "cache"
PULLED = ("events.json", "enrich.json", "geocode.json")


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


def load_raws(city: dict, only: str | None, offline: bool, client: httpx.Client | None,
              offline_root: Path = FIXTURES) -> tuple[list[Raw], dict]:
    """offline reads frozen feeds from offline_root (fixtures, or cache/ for the last fetched copies)."""
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
                    frozen = offline_root / "library" / f"{cid}.ics"
                    if offline and not frozen.exists():
                        continue  # only a few calendars are frozen
                    text = frozen.read_text() if offline else library.fetch(cid, CACHE / "library", client)
                    got += library.parse(text, cid, branches.get(cid))
            else:
                pages = ([json.loads(p.read_text()) for p in sorted((offline_root / "tribe").glob(f"{sid}.p*.json"))]
                         if offline else tribe.fetch(sid, src["url"], CACHE / "tribe", client))
                got += tribe.parse(pages, sid, src["organizer_type"])
            # a venue's copy of another organizer's event, when that organizer's own site disagrees (docs/sources.md)
            skip = re.compile(src["skip"], re.I) if src.get("skip") else None
            kept = [r for r in got if not (skip and skip.search(r.title))]
            stats[sid] = {"parsed": len(kept), **({"skipped": len(got) - len(kept)} if skip else {})}
            raws += kept
        except Exception as e:  # a broken source yields no fresh events; build carries its last good ones
            stats[sid] = {"parsed": 0, "error": f"{type(e).__name__}: {str(e)[:200]}"}
            print(f"source {sid} failed: {e}", file=sys.stderr)
    return raws, stats


def build(only: str | None, offline: bool, no_model: bool, pull_from: str | None) -> int:
    t0 = time.monotonic()
    now = now_utc()
    city = json.loads(CITY.read_text())
    client = httpx.Client(headers={"User-Agent": UA}, timeout=60, follow_redirects=True)
    pulled = pull(pull_from, client) if pull_from else {}

    raws, src_stats = load_raws(city, only, offline, client)
    raws, drops = check.prefilter(raws, now)
    # a partial or fixture build must not be judged against the full snapshot, nor carry from it
    previous = None if (only or offline) else read_json(publish.SNAPSHOT)
    failed = {sid for sid, s in src_stats.items() if "error" in s}
    since, old, old_fields, old_venues = publish.carry(previous or {}, failed, now)
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

    snapshot = publish.compose(raws, fields | old_fields, venues, city, now, previous, since)
    reasons = gate.gate(snapshot, previous, city["boundary"], now, failed)
    candidate = json.dumps(snapshot.model_dump(mode="json", by_alias=True), ensure_ascii=False, default=str)
    public = {str(f.relative_to(ROOT)): f.read_text(errors="replace")
              for f in (ROOT / "site").rglob("*") if f.is_file() and f != publish.SNAPSHOT and "node_modules" not in f.parts}
    reasons += gate.secret_scan({"candidate events.json": candidate, **public})
    for sid, s in src_stats.items():  # a failed source is degraded while it has carried events, then down
        s["published"] = snapshot.sources.get(sid, {}).get("count", 0)
        s["state"] = "active" if sid not in failed else ("degraded" if s["published"] else "down")
        if s["state"] == "degraded":
            s["carried_from"] = since[sid]

    rep = publish.report(now, src_stats, drops, venues, geocoder.calls, enrich_stats, reasons,
                         len(snapshot.events), time.monotonic() - t0)
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
        for raw in load_raws({"sources": [src]}, None, True, None, offline_root=root)[0]:
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


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="jcmaps")
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--source")
    b.add_argument("--offline", action="store_true", help="fixtures instead of feeds; no geocoding or model calls")
    b.add_argument("--no-model", action="store_true")
    b.add_argument("--pull", nargs="?", const="", metavar="URL",
                   help="first fetch the previous snapshot and caches from the live site (default: site_url in city.json)")
    sub.add_parser("eval-enrich")
    a = p.parse_args(argv)
    if a.cmd == "build":
        site_url = None
        if a.pull is not None:
            site_url = a.pull or json.loads(CITY.read_text()).get("site_url")
            if not site_url:
                p.error("--pull needs a URL or site_url in city.json")
        sys.exit(build(a.source, a.offline, a.no_model, site_url))
    sys.exit(eval_enrich())


if __name__ == "__main__":
    main()
