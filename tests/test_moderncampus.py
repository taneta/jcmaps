"""Hudson County Community College's Modern Campus calendar: the public categories at the Jersey City campuses, with
no video-call entries and no meeting link or passcode in any description."""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from pipeline.sources import moderncampus

ROOT = Path(__file__).parent.parent
FIX = ROOT / "fixtures" / "moderncampus" / "hccc.json"
SRC = next(s for s in json.loads((ROOT / "city.json").read_text())["sources"] if s["id"] == "hccc")


def test_hccc_contract():
    items, raws = json.loads(FIX.read_text()), moderncampus.parse(FIX.read_text(), SRC)
    assert len(items) == 105 and len(raws) == 20  # deadlines, admissions visits, virtual and off-campus entries are left out
    assert {r.categories[0] for r in raws} <= set(SRC["categories"])
    assert {r.venue_address for r in raws} == {"70 Sip Ave, Jersey City, NJ", "161 Newkirk St, Jersey City, NJ"}
    screening = next(r for r in raws if r.title.startswith("The Quay Brothers"))
    assert screening.start_utc == datetime(2026, 10, 1, 22, 30, tzinfo=timezone.utc) and screening.date == "2026-10-01"  # 6:30 PM in Jersey City
    assert screening.venue_name.startswith("Gabert Library") and screening.url == "https://www.hccc.edu/calendar/"
    luncheon = next(r for r in raws if r.title.startswith("Subscription Dining"))
    assert luncheon.url.startswith("https://www.payerexpress.com/") and luncheon.categories == ["HCCC Foundation"]
    titles = {e["title"].strip() for e in items} - {r.title for r in raws}
    assert "Virtual Student Financial Aid Workshop" in titles and "Cafecito y Consejos" in titles  # virtual; North Hudson campus


def test_no_meeting_link_or_passcode_reaches_a_record():
    items, raws = json.loads(FIX.read_text()), moderncampus.parse(FIX.read_text(), SRC)
    raw = next(e for e in items if "Board of Trustees" in e["title"])
    assert re.search(r"zoom\.us", raw["descriptionText"]) and re.search(r"passcode", raw["descriptionText"], re.I)
    parsed = next(r for r in raws if "Board of Trustees" in r.title)
    assert not re.search(r"zoom\.us|passcode|https?://", parsed.description, re.I) and parsed.venue_address == "70 Sip Ave, Jersey City, NJ"
    assert moderncampus.MEETING.sub("", "Join https://us02web.zoom.us/j/123 Passcode: 4321 at 6 PM.").split() == ["Join", "at", "6", "PM."]
