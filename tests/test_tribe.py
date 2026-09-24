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


def test_connects_times_are_local_despite_utc_flag():
    raws = tribe.parse(load("connects.p1.json"), "connects", "community")
    assert len(raws) == 38
    r = next(x for x in raws if x.title == "Boogie Fever")
    assert r.start_utc == datetime(2026, 9, 24, 22, 0, tzinfo=timezone.utc)
    assert r.end_utc == datetime(2026, 9, 25, 1, 30, tzinfo=timezone.utc)
    assert r.organizer_type == "unknown"  # the model decides; the source default applies afterwards
