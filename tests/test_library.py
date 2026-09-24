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


def one_event(description: str):
    ics = ("BEGIN:VCALENDAR\r\nX-WR-CALNAME:Main Library\r\nBEGIN:VEVENT\r\nUID:LibCal-1-2-3\r\nSUMMARY:Craft Hour\r\n"
           f"DTSTART:20260926T140000Z\r\nDTEND:20260926T150000Z\r\nDESCRIPTION:{description}\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n")
    return library.parse(ics, "17419", {"name": "Main Library", "address": None})[0]


def test_a_ticket_is_a_fee_only_when_it_is_bought():
    # Bonetti Storytime hands out free entry tickets (#17); a ticket that is bought is still a fee.
    main = library.parse((FIX / "17419.ics").read_text(), "17419", {"name": "Main Library", "address": None})
    bonetti = [r for r in main if r.title == "Bonetti Storytime"]
    assert bonetti and all(r.price == "free" and r.evidence["price"].quote == "library program" for r in bonetti)
    assert one_event("Tickets will be handed out at the door.").price == "free"
    for text in ("Tickets are $5.", "A $10 fee applies.", "Buy your tickets at the desk.", "Tickets are sold at the door.",
                 "Every ticket purchased supports the library."):
        assert one_event(text).price == "unknown", text


def test_money_talk_leaves_the_price_to_the_model():
    # "Free" in the library's own name used to mark ticketed fundraisers free (#24).
    raws = [r for p in FIX.glob("*.ics") for r in library.parse(p.read_text(), p.stem, {"name": p.stem, "address": None})]
    for title in ("The Curious Pint", "Library of Shadows"):
        found = [r for r in raws if r.title.startswith(title)]
        assert found and all(r.price == "unknown" for r in found), title
    talk = next(r for r in raws if r.title == "Author Talk: Katie Yee")  # "copies available for purchase" is a book sale
    assert talk.price == "free" and talk.evidence["price"].quote == "library program"
    assert one_event("A talk at the Jersey City Free Public Library. Tickets are $5.").price == "unknown"


def test_every_feed_parses():
    total = sum(len(library.parse(p.read_text(), p.stem, {"name": p.stem, "address": None})) for p in FIX.glob("*.ics"))
    assert total == 510  # Main, Pavonia, Bookmobile and Spotlight are frozen; they cover every special case
