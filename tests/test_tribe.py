import json
from datetime import datetime, timezone
from pathlib import Path

from pipeline.sources import tribe

FIX = Path(__file__).parent.parent / "fixtures" / "tribe"


def load(*names):
    return [json.loads((FIX / n).read_text()) for n in names]


def test_culture_contract():
    raws = tribe.parse(load("culture.p1.json", "culture.p2.json"), "culture", "city")
    assert len(raws) == 66
    r = raws[0]
    assert r.title == "SMUSH Gallery Artist Talk 2026"
    assert r.start_utc == datetime(2026, 9, 24, 22, 30, tzinfo=timezone.utc) and r.date == "2026-09-24"
    assert r.venue_name == "Smush Gallery" and r.venue_address == "340 Summit Ave, Jersey City, 07306"
    assert r.price == "unknown" and "price" not in r.evidence  # empty cost is unknown, not free
    assert "<" not in r.description and "&amp;" not in r.description
    free = [x for x in raws if x.price == "free"]
    assert len(free) == 2 and all(x.evidence["price"].quote == "free" for x in free)
    kids = [x for x in raws if x.kid_friendly == "yes"]
    assert len(kids) == 2 and kids[0].evidence["kid_friendly"].quote == "kids activities"


def test_riverview_contract():
    raws = tribe.parse(load("riverview.p1.json"), "riverview", "community")
    assert len(raws) == 14
    assert {r.venue_address for r in raws} == {"498 Palisade Ave, Jersey City, 07307", None}  # 2 list no venue
    yoga = next(r for r in raws if r.title == "Yoga in the Park")
    assert yoga.start_utc == datetime(2026, 9, 27, 13, 0, tzinfo=timezone.utc) and yoga.price == "free"
    crafts = next(r for r in raws if r.title == "Free Arts & Crafts with Kelsey")
    assert crafts.price == "unknown"  # an empty cost field; the model can still quote "Free" from the title


def test_connects_times_are_local_despite_utc_flag():
    raws = tribe.parse(load("connects.p1.json"), "connects", "community")
    assert len(raws) == 38
    r = next(x for x in raws if x.title == "Boogie Fever")
    assert r.start_utc == datetime(2026, 9, 24, 22, 0, tzinfo=timezone.utc)
    assert r.end_utc == datetime(2026, 9, 25, 1, 30, tzinfo=timezone.utc)
    assert r.organizer_type == "unknown"  # the model decides; the source default applies afterwards


def test_city_markets_are_free_to_enter_and_other_empty_costs_stay_unknown():
    from pipeline import enrich
    raws = tribe.parse(load("culture.p1.json", "culture.p2.json"), "culture", "city")
    fields = {r.source_uid: enrich.merge(r, None, "city") for r in raws}
    markets = [r for r in raws if "Farmers Market" in r.title]
    assert len(markets) == 12
    assert all(fields[r.source_uid]["price"] == "free" and fields[r.source_uid]["evidence"]["price"].from_ == "rule"
               for r in markets)
    rent = [r for r in raws if r.title == "RENT: The Musical"]
    assert rent and all(fields[r.source_uid]["price"] == "unknown" for r in rent)  # no quote, no default


def test_barrow_mansion_contract_and_its_copies_of_van_vorst_meetings_are_skipped():
    raws = tribe.parse(load("barrow.p1.json", "barrow.p2.json"), "barrow", "community")
    assert len(raws) == 64
    assert {(r.venue_name, r.venue_address) for r in raws} == {("Barrow Mansion", "83 Wayne Street, Jersey City, 07302")}
    vv = [r for r in raws if r.title.startswith("Van Vorst Neighborhood Association Meeting")]
    assert vv[0].date == "2026-10-13"  # the association's own site says October 20
    from pipeline import cli
    barrow = next(s for s in json.loads(cli.CITY.read_text())["sources"] if s["id"] == "barrow")
    kept, stats = cli.load_raws({"sources": [barrow]}, None, cli.FIXTURES, None)
    assert stats["barrow"] == {"parsed": 64 - len(vv), "skipped": len(vv)} and len(vv) == 11
    assert not any("Van Vorst" in r.title for r in kept)
