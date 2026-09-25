import json
import os
import re
import subprocess
import sys
import textwrap
from datetime import datetime, timedelta, timezone
from functools import partial

import httpx
import pytest

from pipeline import cli, enrich, publish
from pipeline.geocode import Geocoder
from pipeline.sources import ical, library, tribe
from pipeline.util import ROOT

T0 = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)
DNS = "[Errno -3] Temporary failure in name resolution"  # culture's fetch on 2026-09-24 (#11, #14)


def test_pull_writes_only_valid_files(tmp_path, monkeypatch):
    monkeypatch.setattr(publish, "SITE_DATA", tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("events.json"):
            return httpx.Response(200, text=json.dumps({"events": []}))
        if request.url.path.endswith("enrich.json"):
            return httpx.Response(200, text="not json")
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    got = cli.pull("https://example.org/jcmaps/", client)
    assert got == {"events.json": "14 bytes", "enrich.json": "JSONDecodeError", "geocode.json": "HTTP 404"}
    assert (tmp_path / "events.json").exists() and not (tmp_path / "enrich.json").exists()


def test_empty_environment_variables_mean_default(monkeypatch):
    from pipeline.util import env
    monkeypatch.setenv("JCMAP_COST_CAP_USD", "")
    assert float(env("JCMAP_COST_CAP_USD", "5")) == 5.0
    monkeypatch.setenv("JCMAP_COST_CAP_USD", "2.5")
    assert float(env("JCMAP_COST_CAP_USD", "5")) == 2.5
    monkeypatch.delenv("JCMAP_MODEL", raising=False)
    assert env("JCMAP_MODEL", "gpt-6-luna") == "gpt-6-luna"


@pytest.fixture
def build(tmp_path, monkeypatch):
    """`jcmaps build` on the frozen feeds as a live run makes it, with no model, no geocoder calls and every file in
    tmp_path: each run's snapshot is the next run's previous one. A source in `down` raises as culture's fetch did
    on 2026-09-24; a source in `empty` answers with no events."""
    city = json.loads(cli.CITY.read_text())
    lib = next(s for s in city["sources"] if s["id"] == "library")
    lib["calendars"] = {c: n for c, n in lib["calendars"].items() if (cli.FIXTURES / "library" / f"{c}.ics").exists()}
    (tmp_path / "city.json").write_text(json.dumps(city))
    monkeypatch.setattr(cli, "CITY", tmp_path / "city.json")
    monkeypatch.setattr(cli, "CACHE", tmp_path / "cache")
    monkeypatch.setattr(publish, "SNAPSHOT", tmp_path / "site" / "data" / "events.json")
    monkeypatch.setattr(publish, "REPORT", tmp_path / "site" / "data" / "report.json")
    monkeypatch.setattr(publish, "REPORTS", tmp_path / "reports")
    monkeypatch.setattr(cli, "Geocoder", lambda query: Geocoder(None, cache_path=tmp_path / "geocode.json"))
    monkeypatch.setattr(enrich, "enrich_all", partial(enrich.enrich_all, cache_path=tmp_path / "enrich.json"))
    monkeypatch.setattr(library, "fetch",
                        lambda cid, cache_dir, client: (cli.FIXTURES / "library" / f"{cid}.ics").read_text())
    monkeypatch.setattr(ical, "fetch",
                        lambda sid, url, cache_dir, client: (cli.FIXTURES / "ical" / f"{sid}.ics").read_text())

    def run(at: datetime, down=(), empty=()) -> tuple[int, dict, dict]:
        def fetch(sid, base, cache_dir, client):
            if sid in down:
                raise httpx.ConnectError(DNS)
            pages = [json.loads(p.read_text()) for p in sorted((cli.FIXTURES / "tribe").glob(f"{sid}.p*.json"))]
            return [{**p, "events": []} for p in pages] if sid in empty else pages
        monkeypatch.setattr(tribe, "fetch", fetch)
        monkeypatch.setattr(cli, "now_utc", lambda: at)
        code = cli.build(None, False, True, None)
        return code, json.loads(publish.REPORT.read_text()), json.loads(publish.SNAPSHOT.read_text())
    return run


def ends(o: dict) -> datetime:
    start = datetime.fromisoformat(o["start_utc"])
    return datetime.fromisoformat(o["end_utc"]) if o["end_utc"] else start + timedelta(hours=2)


def duplicates(rep: dict, source: str) -> dict[str, str]:
    """Dropped duplicate -> the record it gave way to, where either is from the source."""
    return {d["id"]: d["of"] for d in rep["drop_examples"] if d["reason"] == "duplicate" and source in d["id"] + d["of"]}


def test_a_source_that_cannot_be_fetched_keeps_its_last_good_events(build):
    _, rep, first = build(T0)
    assert first["sources"]["culture"] == {"count": 50}
    assert duplicates(rep, "culture:") == {"connects:19676": "culture:10004827", "connects:19964": "culture:44071"}

    later = T0 + timedelta(hours=23)
    code, rep, snap = build(later, down={"culture"})
    assert code == 0 and rep["gate"] == {"passed": True, "reasons": []}
    assert rep["sources"]["culture"] == {"parsed": 0, "error": f"ConnectError: {DNS}", "published": 47,
                                         "state": "degraded", "carried_from": first["generated_at"]}
    assert snap["sources"]["culture"] == {"count": 47, "carried_from": first["generated_at"]}
    published = {e["id"]: e for e in first["events"]}
    assert all(e == published[e["id"]] for e in snap["events"] if e["source_id"] == "culture")  # last_seen included
    carried = {o["event_id"] for o in snap["occurrences"] if o["event_id"].startswith("culture:")}
    ended = {o["event_id"] for o in first["occurrences"] if o["event_id"].startswith("culture:") and ends(o) < later}
    assert "culture:10004827" in ended and not ended & carried  # RENT's night is over
    assert duplicates(rep, "culture:") == {"culture:44071": "connects:19964"}  # the fresh listing of What We Keep wins
    venues = {v["id"] for v in snap["venues"]}
    assert all(o["venue_id"] in venues for o in snap["occurrences"] if o["venue_id"])


def test_events_carried_from_an_older_snapshot_take_the_new_fields_defaults(build):
    build(T0)
    old = json.loads(publish.SNAPSHOT.read_text())
    for e in old["events"]:
        del e["type"]  # as published before event types (#18)
    publish.SNAPSHOT.write_text(json.dumps(old))
    code, rep, snap = build(T0 + timedelta(hours=6), down={"culture"})
    assert code == 0 and rep["sources"]["culture"]["state"] == "degraded"
    assert {e["type"] for e in snap["events"] if e["source_id"] == "culture"} == {"unknown"}


def test_a_source_down_for_a_day_is_left_out_until_it_fetches_again(build):
    _, _, first = build(T0)
    build(T0 + timedelta(hours=12), down={"culture"})
    _, rep, snap = build(T0 + timedelta(hours=23), down={"culture"})
    assert rep["sources"]["culture"]["carried_from"] == first["generated_at"]  # the last fetch, not the last run

    code, rep, snap = build(T0 + timedelta(hours=25), down={"culture"})
    assert code == 0 and rep["gate"]["passed"]
    assert rep["sources"]["culture"] == {"parsed": 0, "error": f"ConnectError: {DNS}", "published": 0, "state": "down"}
    assert "culture" not in snap["sources"] and snap["generated_at"] == (T0 + timedelta(hours=25)).isoformat()

    code, rep, snap = build(T0 + timedelta(hours=26))
    assert code == 0 and rep["sources"]["culture"] == {"parsed": 66, "published": 49, "state": "active"}
    assert snap["sources"]["culture"] == {"count": 49}


def test_a_source_that_answers_with_no_events_still_fails_the_gate(build):
    _, _, first = build(T0)
    code, rep, snap = build(T0 + timedelta(hours=6), empty={"connects"})
    assert code == 2 and rep["gate"]["reasons"] == ["source connects shrank from 34 to 0"]
    assert rep["sources"]["connects"] == {"parsed": 0, "published": 0, "state": "active"}
    assert snap == first  # the last good snapshot stays


def issue(cwd) -> str | None:
    """The build workflow's issue step, run where a build left its report: the issue body, or None for no issue."""
    workflow = (ROOT / ".github" / "workflows" / "build.yml").read_text()
    script = re.search(r"<<'PY'[^\n]*\n(.*?)\n[ \t]*PY\n", workflow, re.S)
    env = {**os.environ, "SERVER": "https://github.com", "REPO": "taneta/jcmaps", "RUN_ID": "1", "TODAY": "2026-09-25"}
    run = subprocess.run([sys.executable, "-"], input=textwrap.dedent(script.group(1)), cwd=cwd, env=env,
                         capture_output=True, text=True)
    assert not run.stderr, run.stderr  # a crash also exits 1, which the step reads as nothing to report
    return run.stdout if run.returncode == 0 else None


def test_the_issue_says_which_source_is_degraded_or_down(build, tmp_path):
    build(T0)
    assert issue(tmp_path) is None
    build(T0 + timedelta(hours=6), down={"culture"})
    assert (f"Source culture could not be fetched (ConnectError: {DNS}). Its last good events, fetched "
            f"{T0.isoformat()}, were carried forward (48 published)") in issue(tmp_path)
    build(T0 + timedelta(hours=25), down={"culture"})
    assert f"Source culture could not be fetched (ConnectError: {DNS}) and has nothing left to carry" in issue(tmp_path)
