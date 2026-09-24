import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pipeline import check
from pipeline.geo import inside
from pipeline.geocode import Geocoder, candidates
from pipeline.model import Venue

CITY = json.loads((Path(__file__).parent.parent / "city.json").read_text())
NOW = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)


def test_boundary():
    assert inside(40.7178, -74.0645, CITY["boundary"])  # Journal Square
    assert inside(40.7189, -74.0473, CITY["boundary"])  # main library
    assert not inside(40.7440, -74.0324, CITY["boundary"])  # Hoboken
    assert not inside(40.7776, -74.0231, CITY["boundary"])  # Union City


def test_drop_reasons(make_raw):
    venues = {"hob": Venue(id="hob", name="Hoboken", lat=40.7440, lon=-74.0324),
              "jc": Venue(id="jc", name="JC", lat=40.7189, lon=-74.0473)}
    raws = [make_raw(source_uid="past", start_utc=NOW - timedelta(days=1), date="2026-09-23"),
            make_raw(source_uid="far", start_utc=NOW + timedelta(days=40), date="2026-11-03"),
            make_raw(source_uid="out", venue_id="hob"),
            make_raw(source_uid="ok", venue_id="jc"),
            make_raw(source_uid="nourl", url=""),
            make_raw(source_uid="closed", title="CLOSED"),
            make_raw(source_uid="closed2", title="Library Closed - Columbus Day")]
    kept, drops = check.prefilter(raws, NOW)
    assert [r.source_uid for r in kept] == ["out", "ok"]
    kept, drops2 = check.check(kept, venues, CITY["boundary"])
    assert [r.source_uid for r in kept] == ["ok"]
    assert {d["id"]: d["reason"] for d in drops + drops2} == {"t:past": "past", "t:far": "beyond_horizon",
                                                                "t:out": "outside_boundary", "t:nourl": "missing_field",
                                                                "t:closed": "closure", "t:closed2": "closure"}


def test_duplicates_keep_more_evidence(make_raw):
    venues = {"a": Venue(id="a", name="A", lat=40.7189, lon=-74.0473), "b": Venue(id="b", name="B", lat=40.7190, lon=-74.0474)}
    rich = make_raw(source_id="library", source_uid="1", title="Toddler Storytime", venue_id="a",
                    evidence={"price": {"quote": "library program", "from": "rule"}})
    poor = make_raw(source_id="connects", source_uid="2", title="Toddler Story Time", venue_id="b",
                    start_utc=datetime(2026, 9, 26, 14, 45, tzinfo=timezone.utc), url="https://y/2")
    other = make_raw(source_uid="3", title="Chess Club", venue_id="a")
    kept, drops = check.check([poor, rich, other], venues, CITY["boundary"])
    assert [r.source_uid for r in kept] == ["1", "3"]
    assert drops == [{"id": "connects:2", "title": "Toddler Story Time", "reason": "duplicate", "of": "library:1"}]
    assert rich.alt_urls == ["https://y/2"]


def test_cancelled_title(make_raw):
    assert check.status_of(make_raw(title="CANCELLED : McGovern Park - Myth, Bookmobile Stop")) == "cancelled"
    assert check.status_of(make_raw(title="Postponed: Family Yoga")) == "cancelled"
    assert check.status_of(make_raw(title="Storytime")) == "scheduled"


def test_geocoder_caches_and_falls_back(tmp_path):
    calls = []

    def fake(q):
        calls.append(q)
        return (40.7, -74.05) if q.startswith("761 Summit Ave") else None

    g = Geocoder(fake, cache_path=tmp_path / "geo.json", min_interval=0)
    qs = candidates("Bookmobile stop: School of Blind, 761 Summit Ave", "School of Blind, 761 Summit Ave")
    assert qs == ["School of Blind, 761 Summit Ave, Jersey City, NJ", "761 Summit Ave, Jersey City, NJ"]
    assert g.lookup(qs) == (40.7, -74.05)
    assert g.lookup(qs) == (40.7, -74.05) and len(calls) == 2  # second lookup served from cache
    assert candidates("Exchange Place", "MONTGOMERY ST BETWEEN HUDSON ST., Jersey City")[-1] == "Exchange Place, Jersey City, NJ"
    assert Geocoder(None, cache_path=tmp_path / "geo.json").lookup(["nowhere"]) is None


def test_secret_scan_catches_key_shapes():
    from pipeline.gate import secret_scan
    assert secret_scan({"a": "hello sk-abcdefghijklmnopqrstuvwxyz12", "b": "ghp_" + "x" * 36, "c": "OPENAI_API_KEY=oops", "d": "fine"}) == [
        "secret-shaped string in a", "secret-shaped string in b", "secret-shaped string in c"]
    assert secret_scan({"page": "ask-me sk-short ghp_short", "slug": "https://x.org/event/desk-lamp-workshop-for-adults-2026/",
                        "key": "sk-proj-Ab12cdEF34ghIJ56klMN78opQR90stUV"}) == ["secret-shaped string in key"]
