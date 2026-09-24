from datetime import datetime, timezone
from pathlib import Path

from pipeline.sources import library

FIX = Path(__file__).parent.parent / "fixtures" / "library"


def test_pavonia_feed_contract():
    raws = library.parse((FIX / "17422.ics").read_text(), "17422", {"name": "Pavonia Branch", "address": "326 8th St"})
    assert len(raws) == 150
    anime = next(r for r in raws if r.title == "Anime Appreciation Club")
    assert anime.start_utc == datetime(2026, 8, 24, 20, 0, tzinfo=timezone.utc)
    assert anime.date == "2026-08-24"
    assert anime.venue_name == "Pavonia Branch" and anime.venue_address == "326 8th St"
    assert anime.kid_friendly == "yes" and anime.evidence["kid_friendly"].quote == "teen programs"
    assert anime.price == "free" and anime.evidence["price"].from_ == "rule"
    assert anime.organizer_type == "city"
    assert "Teen Programs" in anime.topics and "September" not in anime.topics
    assert anime.url == "https://jclibrary.libcal.com/event/17175267" and anime.source_uid == "17175267"


def test_all_day_entries_are_local_midnight():
    raws = library.parse((FIX / "17422.ics").read_text(), "17422", {"name": "Pavonia Branch", "address": None})
    all_day = [r for r in raws if r.all_day]
    assert len(all_day) == 17
    r = all_day[0]
    assert r.start_utc.hour == 4 and r.end_utc.hour == 4  # EDT midnight
    assert (r.end_utc - r.start_utc).days == 1


def test_bookmobile_stops_carry_their_address():
    raws = library.parse((FIX / "17432.ics").read_text(), "17432", None)
    stop = next(r for r in raws if r.title.startswith("School of Blind"))
    assert stop.venue_address == "School of Blind, 761 Summit Ave"
    assert stop.venue_name.startswith("Bookmobile stop:")
    kit = next(r for r in raws if r.title == "Bookmobile Grab & Go Craft Kit")
    assert kit.offsite and kit.venue_name is None


def test_offsite_and_older_adults():
    raws = library.parse((FIX / "17419.ics").read_text(), "17419", {"name": "Main Library", "address": None})
    assert any(r.offsite for r in raws)
    older = [r for r in raws if r.kid_friendly == "no"]
    assert older and all(r.evidence["kid_friendly"].quote == "older adults events" for r in older)
    assert all("Offsite" not in (r.venue_name or "") for r in raws)


def test_every_feed_parses():
    total = sum(len(library.parse(p.read_text(), p.stem, {"name": p.stem, "address": None})) for p in FIX.glob("*.ics"))
    assert total == 510  # Main, Pavonia, Bookmobile and Spotlight are frozen; they cover every special case
