"""The state health calendar's CSV: Jersey City clinics kept, and the columns naming people gone before anything is saved."""
import csv
import io
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx

from pipeline.sources import njdoh

ROOT = Path(__file__).parent.parent
FIX = ROOT / "fixtures" / "njdoh" / "njdoh.csv"
SRC = next(s for s in json.loads((ROOT / "city.json").read_text())["sources"] if s["id"] == "njdoh")


def test_jersey_city_clinics_contract():
    raws = njdoh.parse(FIX.read_text(), SRC)
    assert len(raws) == 6  # of 103 statewide rows
    r = next(x for x in raws if x.date == "2026-09-26")
    assert r.title == "HRHC Vaccination Clinic" and r.organizer_name == "Hudson Regional Health Commission"
    assert r.start_utc == datetime(2026, 9, 26, 15, 0, tzinfo=timezone.utc) and r.end_utc == datetime(2026, 9, 26, 17, 45, tzinfo=timezone.utc)
    assert (r.venue_name, r.venue_address) == ("Jersey City Free Public Library: Cunningham Branch", "275 Martin Luther King Drive, Jersey City, NJ, 07305")
    assert r.url == "https://hudsonregional.gov/programs/vaccination" and r.categories == ["Vaccine clinic"]
    first = next(x for x in raws if x.date == "2026-09-02")
    assert first.url == "https://hudsoncountyvax.org/" and "Walk-ins welcomed" in first.description  # a link inside a sentence
    assert njdoh.when("9/2/2026", "1:00PM") == datetime(2026, 9, 2, 17, 0, tzinfo=timezone.utc) and njdoh.when("9/2/2026", "") is None


def test_the_columns_naming_people_reach_neither_the_fixture_nor_the_cache_nor_a_record(tmp_path):
    assert not njdoh.PERSONAL & set(csv.DictReader(io.StringIO(FIX.read_text())).fieldnames)
    feed = ("Review_Status,Org_Name,Submitter_Email,Event_Name,Event_Date,Start_Time,Venue_City,General_Public,Contact_Phone,Contact_Email,Submitter_Name\n"
            "Approved,An Org,who@example.com,Clinic,10/1/2026,9:00 AM,Jersey City,Yes,201-555-0100,c@example.com,A Person\n")
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, text=feed)))
    text = njdoh.fetch("njdoh", "https://x/calendar.csv", tmp_path, client)
    assert text == (tmp_path / "njdoh.csv").read_text()
    assert not njdoh.PERSONAL & set(csv.DictReader(io.StringIO(text)).fieldnames)
    assert "example.com" not in text and "A Person" not in text and "201-555" not in text
    raw = njdoh.parse(text, SRC)[0]
    assert raw.title == "Clinic" and "@" not in raw.description
