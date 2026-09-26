"""Art House Productions' collection: dates from the titles, times from the text, runs as one span, and no price
from the $0 placeholder."""
import json
from datetime import date, datetime, timezone
from pathlib import Path

from pipeline.sources import arthouse

ROOT = Path(__file__).parent.parent
FIX = ROOT / "fixtures" / "arthouse" / "arthouse.json"
SRC = next(s for s in json.loads((ROOT / "city.json").read_text())["sources"] if s["id"] == "arthouse")


def test_arthouse_contract():
    raws = arthouse.parse(FIX.read_text(), SRC)
    assert len(raws) == 13  # of 15 products: the two gallery months without a day are left out
    focus = next(r for r in raws if r.title.startswith("FOCUS"))
    assert focus.start_utc == datetime(2026, 10, 22, 23, 30, tzinfo=timezone.utc) and focus.end_utc is None and not focus.all_day  # 7:30 PM
    assert focus.venue_address == "345 Marin Blvd, Jersey City, NJ 07302" and focus.organizer_name == "Art House Productions"
    assert focus.url == "https://www.arthouseproductions.org/products/focus-innovative-choreography-series-october-22-2026"
    rent = next(r for r in raws if r.title == "RENT: The Musical")
    assert rent.all_day and rent.date == "2026-09-24" and rent.end_utc == datetime(2026, 10, 19, 4, 0, tzinfo=timezone.utc)  # the run, as one span
    wind = next(r for r in raws if r.title == "IN THE WIND")
    assert (wind.venue_name, wind.venue_address) == ("Lincoln Park", "Lincoln Park, Jersey City, NJ") and wind.all_day
    assert all(r.price == "unknown" and r.cost_text is None for r in raws)  # the $0 placeholder is not a price
    assert arthouse.days("November 2026") is None
    assert arthouse.days("September 11 - October 25 2026") == (date(2026, 9, 11), date(2026, 10, 25))
