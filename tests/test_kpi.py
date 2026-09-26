"""The week's numbers and the coverage matcher, on a small snapshot."""
from datetime import datetime, timezone

from pipeline import cli

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


def ev(i, source, title, price="unknown"):
    return {"id": f"{source}:{i}", "source_id": source, "title": title, "price": price}


def occ(i, source, start, date, venue):
    return {"event_id": f"{source}:{i}", "venue_id": venue, "start_utc": start, "end_utc": None, "all_day": False, "date": date, "tz": "America/New_York"}


SNAP = {"events": [ev(1, "library", "Toddler Storytime", "free"), ev(2, "library", "Chess Club", "free"), ev(3, "culture", "Jazz Night"),
                   ev(4, "culture", "Far Away Fair")],
        "venues": [{"id": "v1", "name": "Pavonia Branch", "lat": 40.72, "lon": -74.04}, {"id": "v2", "name": "Somewhere", "lat": None, "lon": None}],
        "occurrences": [occ(1, "library", "2026-10-02T14:00:00+00:00", "2026-10-02", "v1"), occ(2, "library", "2026-10-03T14:00:00+00:00", "2026-10-03", "v1"),
                        occ(3, "culture", "2026-10-04T23:00:00+00:00", "2026-10-04", "v2"), occ(4, "culture", "2026-10-20T14:00:00+00:00", "2026-10-20", "v1")]}


def test_the_weeks_numbers(capsys):
    out = cli.kpi(None, NOW, SNAP)
    assert out["events_7d"] == 3 and out["by_source"] == {"library": 2, "culture": 1} and out["sources_with_events"] == 2
    assert out["effective_sources"] == 1.8 and out["pinned"] == 0.67 and out["price_known"] == 0.67  # the fair is beyond the week
    assert "events in the next 7 days: 3 (library 2, culture 1)" in capsys.readouterr().out


def test_coverage_counts_a_hit_a_miss_and_a_different_event_on_the_same_day(tmp_path):
    sample = tmp_path / "week.csv"
    sample.write_text("date,title,place,link\n2026-10-02,Toddler Story Time,Pavonia Branch,https://x/1\n"
                      "2026-10-05,Pumpkin Patch,Liberty State Park,https://x/2\n2026-10-03,Knitting Circle,Heights Branch,https://x/3\n")
    out = cli.kpi(sample, NOW, SNAP)
    assert out["coverage"] == {"sample": 3, "shown": 1,
                               "misses": ["2026-10-05 Pumpkin Patch (Liberty State Park)", "2026-10-03 Knitting Circle (Heights Branch)"]}
