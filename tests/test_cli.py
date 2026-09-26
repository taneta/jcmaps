import json
import os
import re
import shutil
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
ERR = f"could not be fetched (ConnectError: {DNS})"


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
    on 2026-09-24; `keep` cuts a source's feed to its first n events (0: an empty answer); a source in `off` is
    switched off in city.json; `cached` builds from the feeds in cache/ as a push to main does."""
    city = json.loads(cli.CITY.read_text())
    lib = next(s for s in city["sources"] if s["id"] == "library")
    lib["calendars"] = {c: n for c, n in lib["calendars"].items() if (cli.FIXTURES / "library" / f"{c}.ics").exists()}
    monkeypatch.setattr(cli, "CITY", tmp_path / "city.json")
    monkeypatch.setattr(cli, "CACHE", tmp_path / "cache")
    monkeypatch.setattr(publish, "SNAPSHOT", tmp_path / "site" / "data" / "events.json")
    monkeypatch.setattr(publish, "REPORT", tmp_path / "site" / "data" / "report.json")
    monkeypatch.setattr(publish, "REPORTS", tmp_path / "reports")
    monkeypatch.setattr(cli, "Geocoder", lambda query: Geocoder(None, cache_path=tmp_path / "geocode.json"))
    monkeypatch.setattr(enrich, "enrich_all", partial(enrich.enrich_all, cache_path=tmp_path / "enrich.json"))

    def run(at: datetime, down=(), keep: dict[str, int] | None = None, off=(), cached=False) -> tuple[int, dict, dict]:
        cli.CITY.write_text(json.dumps({**city, "sources": [{**s, "publish": s.get("publish") and s["id"] not in off}
                                                             for s in city["sources"]]}))

        def fetch_ics(cid, cache_dir, client):
            if "library" in down:
                raise httpx.ConnectError(DNS)
            return (cli.FIXTURES / "library" / f"{cid}.ics").read_text()

        def fetch(sid, base, cache_dir, client):
            if sid in down:
                raise httpx.ConnectError(DNS)
            pages = [json.loads(p.read_text()) for p in sorted((cli.FIXTURES / "tribe").glob(f"{sid}.p*.json"))]
            if keep and sid in keep:
                return [{**pages[0], "events": [e for p in pages for e in p["events"]][:keep[sid]]}]
            return pages
        def fetch_ical(sid, url, cache_dir, client):
            if sid in down:
                raise httpx.ConnectError(DNS)
            return (cli.FIXTURES / "ical" / f"{sid}.ics").read_text()
        monkeypatch.setattr(library, "fetch", fetch_ics)
        monkeypatch.setattr(tribe, "fetch", fetch)
        monkeypatch.setattr(ical, "fetch", fetch_ical)
        monkeypatch.setattr(cli, "now_utc", lambda: at)
        code = cli.build(None, False, True, None, cached)
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
    assert rep["sources"]["culture"] == {"parsed": 0, "error": ERR, "published": 47,
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
    assert rep["sources"]["culture"] == {"parsed": 0, "error": ERR, "published": 0, "state": "down"}
    assert "culture" not in snap["sources"] and snap["generated_at"] == (T0 + timedelta(hours=25)).isoformat()

    code, rep, snap = build(T0 + timedelta(hours=26))
    assert code == 0 and rep["sources"]["culture"] == {"parsed": 66, "published": 49, "state": "active"}
    assert snap["sources"]["culture"] == {"count": 49}


def test_a_feed_that_lists_far_fewer_events_is_carried_for_a_day_then_published_as_it_is(build, tmp_path):
    _, _, first = build(T0)
    assert first["sources"]["connects"] == {"count": 34}
    code, rep, snap = build(T0 + timedelta(hours=6), keep={"connects": 18})
    assert code == 0 and rep["gate"]["passed"] and snap["generated_at"] == (T0 + timedelta(hours=6)).isoformat()
    assert rep["sources"]["connects"] == {"parsed": 18, "error": "shrank from 34 to 18", "published": 34,
                                          "state": "degraded", "carried_from": first["generated_at"]}
    assert f"Source connects shrank from 34 to 18. Its last good events, fetched {T0.isoformat()}" in issue(tmp_path)

    code, rep, snap = build(T0 + timedelta(hours=25), keep={"connects": 18})  # a day later, the smaller feed it is
    assert code == 0 and rep["sources"]["connects"] == {"parsed": 18, "error": "shrank from 34 to 14", "published": 13,
                                                        "state": "active"}  # 4 of the 18 are over by then
    assert "Source connects shrank from 34 to 14, and its last good events are past carrying, so its smaller feed is published as it is" in issue(tmp_path)
    code, rep, snap = build(T0 + timedelta(hours=30), keep={"connects": 18})  # and the comparison has settled
    assert rep["sources"]["connects"] == {"parsed": 18, "published": 13, "state": "active"} and issue(tmp_path) is None


def test_switching_a_source_off_publishes_on_the_next_run(build):
    build(T0)
    code, rep, snap = build(T0 + timedelta(hours=6), off={"connects"})
    assert code == 0 and rep["gate"]["passed"] and "connects" not in rep["sources"] and "connects" not in snap["sources"]


def test_a_feed_that_parses_to_a_few_events_or_none_is_still_flagged(build, tmp_path):
    _, _, first = build(T0)
    code, rep, snap = build(T0 + timedelta(hours=6), keep={"connects": 2})
    assert code == 0 and rep["sources"]["connects"] == {"parsed": 2, "error": "shrank from 34 to 2", "published": 34,
                                                        "state": "degraded", "carried_from": first["generated_at"]}
    assert "Source connects shrank from 34 to 2. Its last good events" in issue(tmp_path)
    code, rep, snap = build(T0 + timedelta(hours=25), keep={"connects": 0})
    assert code == 0 and rep["gate"]["passed"] and "connects" not in snap["sources"]
    assert rep["sources"]["connects"] == {"parsed": 0, "error": "shrank from 34 to 0", "published": 0, "state": "down"}
    assert "Source connects shrank from 34 to 0 and has nothing left to carry, so it is left out until its feed answers with events again" in issue(tmp_path)


def issue(cwd) -> str | None:
    """The build workflow's issue step, run where a build left its report: the issue body, or None for no issue."""
    workflow = (ROOT / ".github" / "workflows" / "build.yml").read_text()
    script = re.search(r"<<'PY'[^\n]*\n(.*?)\n[ \t]*PY\n", workflow, re.S)
    env = {**os.environ, "SERVER": "https://github.com", "REPO": "taneta/jcmaps", "RUN_ID": "1"}
    run = subprocess.run([sys.executable, "-"], input=textwrap.dedent(script.group(1)), cwd=cwd, env=env,
                         capture_output=True, text=True)
    assert not run.stderr, run.stderr  # a crash also exits 1, which the step reads as nothing to report
    return run.stdout if run.returncode == 0 else None


def issue_step(cwd, open_issue: str = "") -> list[str]:
    """The whole issue step, shell included, with a fake `gh` that answers `issue list` with open_issue and records
    every call. Returns the calls, one per line."""
    workflow = (ROOT / ".github" / "workflows" / "build.yml").read_text()
    script = textwrap.dedent(re.search(r"Open an issue.*?run: \|\n(.*?)\n\n", workflow, re.S).group(1))
    gh = cwd / "bin" / "gh"
    gh.parent.mkdir(exist_ok=True)
    gh.write_text('#!/bin/sh\necho "$@" >> "$GH_LOG"\ncase "$*" in *"issue list"*) echo "$OPEN_ISSUE";; esac\n')
    gh.chmod(0o755)
    env = {**os.environ, "PATH": f"{gh.parent}:{os.environ['PATH']}", "GH_LOG": str(cwd / "gh.log"), "OPEN_ISSUE": open_issue,
           "SERVER": "https://github.com", "REPO": "taneta/jcmaps", "RUN_ID": "1"}
    subprocess.run(["bash", "-e", "-c", script], cwd=cwd, env=env, capture_output=True, text=True, check=True)
    calls = (cwd / "gh.log").read_text().splitlines() if (cwd / "gh.log").exists() else []
    (cwd / "gh.log").unlink(missing_ok=True)
    return calls


def test_a_lasting_failure_comments_on_the_open_issue_instead_of_opening_another(build, tmp_path):
    build(T0)
    assert issue_step(tmp_path) == []  # nothing to report, so gh is not called at all
    build(T0 + timedelta(hours=6), down={"culture"})
    calls = issue_step(tmp_path)
    assert calls[-1].startswith("issue create --title Build ") and calls[-1].endswith("--body-file /tmp/issue.md --label auto:build")
    calls = issue_step(tmp_path, open_issue="12")
    assert calls[-1] == "issue comment 12 --body-file /tmp/issue.md" and not any("issue create" in c for c in calls)


def test_the_issue_says_which_source_is_degraded_or_down(build, tmp_path):
    build(T0)
    assert issue(tmp_path) is None
    build(T0 + timedelta(hours=6), down={"culture"})
    body = issue(tmp_path)
    assert f"**Seen:** run report, {(T0 + timedelta(hours=6)).isoformat()} ([run](" in body  # the run's time, from the report
    assert (f"Source culture could not be fetched (ConnectError: {DNS}). Its last good events, fetched "
            f"{T0.isoformat()}, were carried forward (48 published)") in body
    build(T0 + timedelta(hours=25), down={"culture"})
    assert f"Source culture could not be fetched (ConnectError: {DNS}) and has nothing left to carry" in issue(tmp_path)


def test_a_push_builds_from_the_saved_feeds_without_a_request(build):
    _, fetched, first = build(T0)
    for kind in ("library", "tribe", "ical"):
        shutil.copytree(cli.FIXTURES / kind, cli.CACHE / kind)  # what the last fetching run saved
    code, rep, snap = build(T0, down={"library", "culture", "connects", "city"}, cached=True)  # any fetch would raise
    assert code == 0 and rep["sources"] == fetched["sources"] and snap["events"] == first["events"]

    shutil.rmtree(cli.CACHE)  # nothing saved yet: every source is carried, and the report says what is missing
    code, rep, snap = build(T0 + timedelta(hours=2), cached=True)
    assert code == 0 and {s["state"] for sid, s in rep["sources"].items() if sid in first["sources"]} == {"degraded"}
    assert rep["sources"]["culture"]["error"].startswith("could not be fetched (FileNotFoundError")
    assert {e["id"] for e in snap["events"]} <= {e["id"] for e in first["events"]}


def test_requests_to_a_host_are_spaced_as_its_robots_txt_asks(monkeypatch):
    from pipeline import util
    clock, naps = [0.0], []

    def sleep(s):
        naps.append(s)
        clock[0] += s
    monkeypatch.setattr(util.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(util.time, "sleep", sleep)
    wait = util.spaced({"jclibrary.libcal.com": 10})
    for url in ("https://jclibrary.libcal.com/a", "https://jclibrary.libcal.com/b", "https://jerseycityculture.org/x",
                "https://jclibrary.libcal.com/c"):
        wait(httpx.Request("GET", url))
        clock[0] += 1  # each request takes a second
    assert naps == [9, 8]  # the library's requests land 10 s apart; the city site's one waits for nothing
    assert "+https://jcmaps.com" in util.UA


def test_score_enrich_counts_agreement_with_the_labeled_set_offline():
    from pipeline.llm import Call
    rows = json.loads((cli.FIXTURES / "labeled" / "enrich.json").read_text())
    by_input = {r["input"]: r for r in rows}
    fields = ("kid_friendly", "price", "registration", "organizer_type", "status")

    def perfect(text):  # a model that answers what the labels say, with their quotes
        e, q = by_input[text]["expected"], by_input[text]["quotes"]
        out = {f: e[f] for f in fields} | {f"{f}_quote": q.get(f) for f in fields}
        out |= {"age_text": e["age_text"], "age_min": None, "age_max": None, "topics": [], "summary": "s", "price_text": None,
                "venue_name": None, "venue_address": None, "venue_quote": None}
        return Call(input_hash="x", model="fake", out=out, cost_usd=0.001)

    result = cli.score_enrich(perfect)
    assert result["misses"] == [] and result["agree"] == result["seen"] and result["cost_usd"] == 0.03
    # labels an adapter rule decided (a library storytime is for kids, free, the city's) are not the model's to score;
    # a label corrected to unknown counts even where the model had quoted something
    assert result["seen"] == {"kid_friendly": 24, "price": 19, "registration": 30, "organizer_type": 9, "status": 30, "age_text": 30}

    blind = lambda text: Call(input_hash="x", model="fake", out=None)  # proves nothing: the unknown labels still agree
    result = cli.score_enrich(blind)
    assert result["agree"]["kid_friendly"] == 16 and result["seen"]["kid_friendly"] == 24
    assert "kid_friendly: expected 'yes', got 'unknown'" in "\n".join(result["misses"])
def test_the_issue_for_a_run_that_wrote_no_report_says_so_with_the_current_time(tmp_path):
    body = issue(tmp_path)  # no site/data/report.json here
    assert re.search(r"\*\*Seen:\*\* run report, \d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+00:00 \(\[run\]", body)
    assert "The run stopped before writing a report" in body
