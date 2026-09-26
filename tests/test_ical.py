"""The general iCal adapter on the city's frozen calendar, and the iCal rules any feed can hit."""
import json
from datetime import datetime, timezone
from pathlib import Path

from pipeline.geocode import venue_key
from pipeline.sources import ical

ROOT = Path(__file__).parent.parent
FEED = ROOT / "fixtures" / "ical" / "city.ics"
CITY = next(s for s in json.loads((ROOT / "city.json").read_text())["sources"] if s["id"] == "city")
WINDOW = (datetime(2026, 9, 24, tzinfo=timezone.utc), datetime(2026, 10, 26, tzinfo=timezone.utc))


def utc(*args) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


def test_city_contract():
    raws = ical.parse(FEED.read_text(), CITY, WINDOW)
    assert len(raws) == 120  # of 122 entries; the two repeating ones have no date before October 2027
    assert len([r for r in raws if WINDOW[0] <= r.start_utc < WINDOW[1]]) == 19
    r = next(x for x in raws if x.source_uid == "21343556")
    assert r.title == "City Council Meeting" and r.organizer_name == "City of Jersey City"
    assert r.start_utc == utc(2026, 10, 7, 22, 0) and r.date == "2026-10-07"
    assert r.venue_name == "Council Chambers" and r.venue_address == "280 Grove St., Jersey City NJ 07302"
    assert r.url == "https://www.jerseycitynj.gov/workspaces/one.aspx?objectId=21343556&contextId=12409811"
    assert r.description.startswith("Stream Live via Microsoft Teams") and "<" not in r.description


def test_city_locations_become_one_venue_per_address_or_none():
    raws = {r.source_uid: r for r in ical.parse(FEED.read_text(), CITY, WINDOW)}
    assert (raws["21059936"].venue_name, raws["21059936"].venue_address) == ("City Hall", "280 Grove St, Jersey City, NJ")
    assert (raws["21342927"].venue_name, raws["21342927"].venue_address) == (
        "1st floor Board Room of the Holloway Building", "4 Jackson Square, Jersey City, NJ")  # "NJ 0730" cut off
    assert all(raws[u].venue_name is None and raws[u].venue_address is None
               for u in ("21245783", "21394407"))  # "Zoom" and an empty location: listed without a pin
    keys = {venue_key(raws[u].venue_name, raws[u].venue_address) for u in ("21059936", "21343556")}
    assert keys == {"280 grove st, jersey city"}  # City Hall and Council Chambers share one pin
    assert ical.place("Zoom (link in description)", {}) == (None, None)
    assert ical.place("Boardroom at the Holloway Building, City Hall Annex", CITY["places"]) == (
        "Holloway Building", "4 Jackson Square, Jersey City, NJ")  # the annex's other spelling names no street
    assert ical.place("Islamic Center of Jersey City 17 Park Street", {}) == ("Islamic Center of Jersey City", "17 Park Street")


def test_a_feed_is_unfolded_and_scrubbed_as_it_is_read(tmp_path):
    import httpx
    feed = "BEGIN:VCALENDAR\r\nDESCRIPTION:Email clerk@jc\r\n nj.org or call 201-\r\n 547-5000.\r\nEND:VCALENDAR\r\n"
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, text=feed)))
    text = ical.fetch("city", "https://example.org/city.ics", tmp_path, client)
    assert text == (tmp_path / "city.ics").read_bytes().decode()
    assert text == "BEGIN:VCALENDAR\r\nDESCRIPTION:Email name@example.org or call 000-000-0000.\r\nEND:VCALENDAR\r\n"


CAL = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:yoga
SUMMARY:Park yoga
DTSTART;TZID=America/New_York:20260802T090000
DTEND;TZID=America/New_York:20260802T100000
RRULE:FREQ=WEEKLY;BYDAY=SU
EXDATE;TZID=America/New_York:20261011T090000
LOCATION:Riverview-Fisk Park
URL:https://example.org/yoga
CATEGORIES:Health
END:VEVENT
BEGIN:VEVENT
UID:yoga
RECURRENCE-ID;TZID=America/New_York:20261004T090000
DTSTART;TZID=America/New_York:20261004T110000
DTEND;TZID=America/New_York:20261004T120000
SUMMARY:Park yoga, late start
URL:https://example.org/yoga
CATEGORIES:Health
END:VEVENT
BEGIN:VEVENT
UID:yoga
RECURRENCE-ID;TZID=America/New_York:20261018T090000
DTSTART;TZID=America/New_York:20261018T090000
SUMMARY:Park yoga
STATUS:CANCELLED
END:VEVENT
BEGIN:VEVENT
UID:talk
SUMMARY:Evening talk
DTSTART:20261001T190000
DTEND:20261001T203000
LOCATION:via Zoom
END:VEVENT
BEGIN:VEVENT
UID:fair
SUMMARY:Street fair
DTSTART;VALUE=DATE:20261003
DTEND;VALUE=DATE:20261005
LOCATION:Newark Avenue pedestrian plaza
END:VEVENT
BEGIN:VEVENT
UID:busy
SUMMARY:Busy
CLASS:PRIVATE
DTSTART:20261002T160000Z
END:VEVENT
BEGIN:VEVENT
UID:gone
SUMMARY:Park cleanup
STATUS:CANCELLED
DTSTART:20261002T140000Z
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n")
SRC = {"id": "test", "name": "A test calendar", "link": "https://example.org/events/{uid}"}


def test_repeating_events_become_one_record_per_date_in_the_window():
    raws = {r.source_uid: r for r in ical.parse(CAL, SRC, WINDOW)}
    yoga = sorted((u, r.start_utc, r.title) for u, r in raws.items() if u.startswith("yoga"))
    assert yoga == [  # every Sunday, less the EXDATE (Oct 11) and the cancelled date (Oct 18); Oct 4 moved to 11am
        ("yoga@20260927T0900", utc(2026, 9, 27, 13, 0), "Park yoga"),
        ("yoga@20261004T0900", utc(2026, 10, 4, 15, 0), "Park yoga, late start"),
        ("yoga@20261025T0900", utc(2026, 10, 25, 13, 0), "Park yoga"),
    ]
    assert raws["yoga@20261025T0900"].end_utc == utc(2026, 10, 25, 14, 0)
    assert "busy" not in raws and "gone" not in raws  # private and cancelled entries are skipped


def test_floating_times_all_day_entries_links_and_category_filter():
    raws = {r.source_uid: r for r in ical.parse(CAL, SRC, WINDOW)}
    talk = raws["talk"]
    assert (talk.start_utc, talk.end_utc) == (utc(2026, 10, 1, 23, 0), utc(2026, 10, 2, 0, 30))  # Jersey City time
    assert talk.venue_name is None and talk.url == "https://example.org/events/talk"
    fair = raws["fair"]
    assert fair.all_day and fair.date == "2026-10-03" and fair.end_utc == utc(2026, 10, 5, 4, 0)
    assert (fair.venue_name, fair.venue_address) == ("Newark Avenue pedestrian plaza", None)
    health = ical.parse(CAL, {**SRC, "categories": ["health"]}, WINDOW)
    assert {r.source_uid for r in health} == {"yoga@20260927T0900", "yoga@20261004T0900", "yoga@20261025T0900"}
