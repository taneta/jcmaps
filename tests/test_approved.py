"""Events approved from the suggestion form: a short list in the repo, published like a feed's events."""
import json
from datetime import datetime, timezone
from pathlib import Path

from pipeline import check
from pipeline.sources import approved

ROOT = Path(__file__).parent.parent
SRC = next(s for s in json.loads((ROOT / "city.json").read_text())["sources"] if s["id"] == "approved")
NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


def test_an_approved_event_publishes_with_its_link_and_price_and_a_past_one_drops_off():
    raws = approved.parse((ROOT / "fixtures" / "approved" / "approved.json").read_text(), SRC)
    assert len(raws) == 2
    kept, drops = check.prefilter(raws, NOW)
    assert [r.title for r in kept] == ["Fall Book Swap"] and [d["reason"] for d in drops] == ["past"]
    r = kept[0]
    assert r.start_utc == datetime(2026, 10, 10, 18, 0, tzinfo=timezone.utc) and r.date == "2026-10-10"  # 2 PM in Jersey City
    assert (r.venue_name, r.venue_address, r.url) == ("Van Vorst Park", "Jersey Ave & Montgomery St, Jersey City, NJ", "https://example.org/book-swap")
    assert r.price == "free" and r.kid_friendly == "yes" and r.evidence["price"].from_ == "rule"
    assert r.organizer_name == "Friends of Van Vorst Park"
    past = next(x for x in raws if x.title.startswith("Summer"))
    assert past.url == SRC["link"] and past.price == "unknown" and past.end_utc is None  # no link: the About page


def test_the_repo_list_is_read_like_a_feed(tmp_path):
    text = approved.fetch("approved", SRC["url"], tmp_path, None)
    assert isinstance(json.loads(text), list) and (tmp_path / "approved.json").read_text() == text
