import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pipeline import check, cli
from pipeline.geo import inside
from pipeline.geocode import Geocoder, build_venues, candidates, venue_key
from pipeline.model import Venue

CITY = json.loads((Path(__file__).parent.parent / "city.json").read_text())
NOW = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)
COMMUNIPAW = [("library", "Communipaw Branch", "295 Johnston Ave, Jersey City, NJ"),  # one branch, three spellings (#2)
              ("culture", "COMMUNIPAW BRANCH LIBRARY", "295 JOHNSTON AVE., Jersey City, 07304"),
              ("connects", "Communipaw Branch", "295 Johnston Ave, Jersey City, 07304")]


def one_point(tmp_path) -> Geocoder:
    """Every query lands on the Communipaw branch, as Nominatim put Bethune Park and the amphitheater on one point."""
    return Geocoder(lambda q: (40.71215, -74.056565), cache_path=tmp_path / "geo.json", min_interval=0)


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
    venues = {"a": Venue(id="a", name="A", lat=40.7189, lon=-74.0473)}
    rich = make_raw(source_id="library", source_uid="1", title="Toddler Storytime", venue_id="a",
                    evidence={"price": {"quote": "library program", "from": "rule"}})
    poor = make_raw(source_id="connects", source_uid="2", title="Toddler Story Time", venue_id="a",
                    start_utc=datetime(2026, 9, 26, 14, 45, tzinfo=timezone.utc), url="https://y/2")
    other = make_raw(source_uid="3", title="Chess Club", venue_id="a")
    kept, drops = check.check([poor, rich, other], venues, CITY["boundary"])
    assert [r.source_uid for r in kept] == ["1", "3"]
    assert drops == [{"id": "connects:2", "title": "Toddler Story Time", "reason": "duplicate", "of": "library:1"}]
    assert rich.alt_urls == ["https://y/2"]


def test_three_listings_of_one_event_become_one(make_raw, tmp_path):
    """"What We Keep" on Sat Sep 26: Connects lists 2 to 4 PM inside the others' 1 to 5 PM, and Cultural Affairs
    shares only the first three words of the title."""
    at = lambda h: datetime(2026, 9, 26, h, tzinfo=timezone.utc)
    title = "WHAT WE KEEP: Artist Talk & Mini-photobook Workshop"
    (_, lib_name, lib_addr), (_, cul_name, cul_addr), (_, con_name, con_addr) = COMMUNIPAW
    lib = make_raw(source_id="library", source_uid="17233848", title=title, url="https://lib/1", start_utc=at(17), end_utc=at(21),
                   venue_name=lib_name, venue_address=lib_addr, evidence={"price": {"quote": "library program", "from": "rule"}})
    cul = make_raw(source_id="culture", source_uid="44071", title="What We Keep 2026", url="https://cul/1",
                   start_utc=at(17), end_utc=at(21), venue_name=cul_name, venue_address=cul_addr)
    con = make_raw(source_id="connects", source_uid="19964", title=title, url="https://con/1", start_utc=at(18), end_utc=at(20),
                   venue_name=con_name, venue_address=con_addr)
    after = make_raw(source_id="library", source_uid="2", title=title, url="https://lib/2", start_utc=at(21), end_utc=at(22),
                     venue_name=lib_name, venue_address=lib_addr)  # a later session, back to back: not a duplicate
    raws = [con, cul, lib, after]
    kept, drops = check.check(raws, build_venues(raws, one_point(tmp_path)), CITY["boundary"])
    assert [r.id for r in kept] == ["library:17233848", "library:2"]
    assert lib.alt_urls == ["https://con/1", "https://cul/1"]
    assert [(d["id"], d["of"]) for d in drops] == [("connects:19964", "library:17233848"), ("culture:44071", "library:17233848")]


def test_one_venue_per_address(make_raw, tmp_path):
    raws = [make_raw(source_id=s, source_uid=s, venue_name=n, venue_address=a) for s, n, a in COMMUNIPAW]
    raws += [make_raw(source_uid="park", venue_name="Mary McLeod Bethune Park", venue_address="43 Martin Luther King Drive, Jersey City, 07305"),
             make_raw(source_uid="amph", venue_name="Glenn D. Cunningham Branch Library Amphitheater",
                      venue_address="275 Martin Luther King Drive, Jersey City, NJ 07305"),
             make_raw(source_uid="hob", venue_name="Grand Street Branch", venue_address="124 Grand St, Hoboken, 07030"),
             make_raw(source_uid="jc", venue_name="Somewhere", venue_address="124 Grand Street, Jersey City"),
             make_raw(source_id="library", source_uid="c", venue_name="Bookmobile stop: Canceled- 222 Laidlaw Ave.",
                      venue_address="Canceled- 222 Laidlaw Ave."),
             make_raw(source_id="library", source_uid="s", venue_name="Bookmobile stop: MS. 7, 222 Laidlaw Ave.",
                      venue_address="MS. 7, 222 Laidlaw Ave.")]
    venues = build_venues(raws, one_point(tmp_path))
    communipaw = venues[raws[0].venue_id]
    assert raws[1].venue_id == raws[2].venue_id == communipaw.id == "295-johnston-ave-jersey-city"
    assert (communipaw.name, communipaw.aliases, communipaw.kind) == ("Communipaw Branch", ["COMMUNIPAW BRANCH LIBRARY"], "library")
    assert raws[3].venue_id != raws[4].venue_id  # one point, two addresses: two venues
    assert raws[5].venue_id != raws[6].venue_id  # Hoboken has a Grand St too
    assert venues[raws[7].venue_id].name == "Bookmobile stop: MS. 7, 222 Laidlaw Ave."  # not the cancelled stop's label
    assert len(venues) == 6


def test_fixture_venue_table_has_one_venue_per_address(tmp_path):
    first = {"sources": [s for s in CITY["sources"] if s["id"] in ("library", "culture", "connects")]}  # day one's
    raws, _ = cli.load_raws(first, None, cli.FIXTURES, None)
    venues = build_venues(raws, Geocoder(None, cache_path=tmp_path / "geo.json"))
    keys = [venue_key(v.name, v.address) for v in venues.values()]
    assert len(keys) == len(set(keys))
    assert len(venues) == 90  # 105 distinct name and address pairs
    art = next(v for v in venues.values() if v.id == "345-marin-blvd-jersey-city")
    assert (art.name, art.aliases) == ("Art House Productions", ["ART HOUSE"])  # mixed case over all caps


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
