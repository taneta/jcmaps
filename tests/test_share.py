"""Share links: a readable name per event that never changes, a page whose tags make a chat preview the event (the
day and start time first), and a preview image a chat accepts. Drawing the map needs Chrome and the network, so it
is checked by hand and in the run report (share.maps_drawn), not here."""
from datetime import datetime, timezone

from PIL import Image

from pipeline import publish, share

CITY = {"site_url": "https://jcmaps.com/", "tz": "America/New_York", "name": "Jersey City", "center": [0, 0],
        "bbox": [0, 0, 0, 0]}
FIELDS = dict(organizer_type="city", topics=[], type="unknown", kid_friendly="unknown", age_min=None, age_max=None,
              age_text=None, price="unknown", price_text=None, registration="unknown", summary=None, status="scheduled",
              evidence={})


def snapshot() -> dict:
    return {
        "events": [{"id": "city:1", "slug": "2026-10-07-city-council-meeting", "title": "City Council Meeting",
                    "summary": "The council's regular public meeting.", "ongoing": False},
                   {"id": "city:2", "slug": "2026-10-20-environmental-commission-meeting",
                    "title": "Environmental Commission Meeting", "summary": None, "ongoing": False}],
        "occurrences": [{"event_id": "city:1", "venue_id": "v1", "start_utc": "2026-10-07T22:00:00+00:00",
                         "end_utc": None, "all_day": False},
                        {"event_id": "city:2", "venue_id": None, "start_utc": "2026-10-20T22:30:00+00:00",
                         "end_utc": None, "all_day": False}],
        "venues": [{"id": "v1", "name": "Council Chambers", "address": "280 Grove St., Jersey City NJ 07302",
                    "lat": 40.7178, "lon": -74.0431}],
    }


def test_names_are_readable_unique_per_day_and_kept_once_published():
    events = [("a", "2026-10-07", "City Council Meeting"), ("b", "2026-10-07", "City Council Meeting"),
              ("c", "2026-10-08", "Café Night: Jazz & Poetry!")]
    assert share.slugs(events, {}) == {"a": "2026-10-07-city-council-meeting", "b": "2026-10-07-city-council-meeting-2",
                                       "c": "2026-10-08-cafe-night-jazz-poetry"}
    renamed = [("a", "2026-10-07", "CANCELLED: City Council Meeting")] + events[1:]  # the published name stays
    assert share.slugs(renamed, {"a": {"slug": "2026-10-07-city-council-meeting"}})["a"] == "2026-10-07-city-council-meeting"
    long = share.words("word " * 40)
    assert len(long) <= 60 and not long.endswith("-")


def test_compose_names_new_events_and_keeps_published_names(make_raw):
    now = datetime(2026, 9, 26, 12, tzinfo=timezone.utc)
    raws = [make_raw(source_uid="1", title="Storytime"), make_raw(source_uid="2", title="Storytime")]
    first = publish.compose(raws, {r.id: FIELDS for r in raws}, {}, CITY, now, None).model_dump(mode="json")
    assert [e["slug"] for e in first["events"]] == ["2026-09-26-storytime", "2026-09-26-storytime-2"]
    raws[0].title = "Storytime (moved inside)"
    again = publish.compose(raws, {r.id: FIELDS for r in raws}, {}, CITY, now, first).model_dump(mode="json")
    assert [e["slug"] for e in again["events"]] == ["2026-09-26-storytime", "2026-09-26-storytime-2"]


def test_the_description_opens_with_the_day_and_start_time_in_jersey_city_time():
    occ = {"start_utc": "2026-10-07T22:00:00+00:00", "end_utc": None, "all_day": False}
    place = share.place_text({"name": "Council Chambers", "address": "280 Grove St., Jersey City NJ 07302"})
    assert share.description(share.when_text(occ), place, "The council's regular public meeting.") == (
        "Wed, Oct 7 · 6 PM · Council Chambers, 280 Grove St. The council's regular public meeting.")
    assert share.when_text({**occ, "start_utc": "2026-10-07T22:30:00+00:00"}) == "Wed, Oct 7 · 6:30 PM"
    all_day = {"start_utc": "2026-10-03T04:00:00+00:00", "end_utc": "2026-10-26T04:00:00+00:00", "all_day": True}
    assert share.when_text(all_day) == "Sat, Oct 3 · All day"
    assert share.when_text(all_day, ongoing=True) == "Sat, Oct 3 to Sun, Oct 25"  # an exhibition, its end exclusive
    assert share.description("Tue, Oct 20 · 6:30 PM", None, None) == "Tue, Oct 20 · 6:30 PM"  # no place, no summary
    assert share.place_text({"name": "181 Cottonwood St", "address": "181 Cottonwood St"}) == "181 Cottonwood St"


def test_a_page_carries_the_preview_tags_and_sends_visitors_to_the_map():
    ev = {"title": 'Film & Talk: "Home"', "slug": "2026-10-07-film-talk-home"}
    url = "https://jcmaps.com/e/2026-10-07-film-talk-home/"
    text = share.page(ev, "Wed, Oct 7 · 6 PM · Barrow Mansion, 83 Wayne Street", url, url + "preview.jpg", "A map")
    assert '<meta property="og:title" content="Film &amp; Talk: &quot;Home&quot;">' in text
    assert '<meta property="og:description" content="Wed, Oct 7 · 6 PM · Barrow Mansion, 83 Wayne Street">' in text
    assert f'<meta property="og:image" content="{url}preview.jpg">' in text and f'<link rel="canonical" href="{url}">' in text
    assert '<meta name="twitter:card" content="summary_large_image">' in text
    assert 'location.replace("../../#e=2026-10-07-film-talk-home")' in text
    assert '<meta name="twitter:card" content="summary">' in share.page(ev, "d", url, None, "")  # no image: a small card


def test_publish_writes_a_page_and_a_preview_per_event_and_rebuilds_the_folder(tmp_path):
    stale = tmp_path / "site" / "e" / "2026-09-01-over" / "index.html"
    stale.parent.mkdir(parents=True)
    stale.write_text("an event that is no longer published")
    stats = share.publish(snapshot(), CITY, tmp_path / "site", tmp_path / "maps", "text")
    assert stats == {"pages": 2, "maps_drawn": 0, "maps_cached": 0, "without_map": 2}
    assert not stale.exists()
    folder = tmp_path / "site" / "e" / "2026-10-07-city-council-meeting"
    assert "Wed, Oct 7 · 6 PM · Council Chambers, 280 Grove St. The council" in (folder / "index.html").read_text()
    with Image.open(folder / "preview.jpg") as im:
        assert im.size == (1200, 630) and im.format == "JPEG"
    assert (folder / "preview.jpg").stat().st_size < 300_000  # WhatsApp's limit for a preview image


def test_a_saved_map_goes_under_the_pin_and_without_chrome_nothing_is_drawn(tmp_path, monkeypatch):
    maps = tmp_path / "maps"
    maps.mkdir()
    Image.new("RGB", (1200, 630)).save(maps / "40.71780_-74.04310.jpg")  # the council's point, drawn on an earlier run
    monkeypatch.setattr(share, "chrome", lambda: None)
    stats = share.publish(snapshot(), CITY, tmp_path / "site", maps, "maps")
    assert stats == {"pages": 2, "maps_drawn": 0, "maps_cached": 1, "without_map": 1}  # the Zoom meeting has no pin
    assert share.render_maps({"a": (40.7, -74.0)}, maps) == 0
