from pipeline import enrich
from pipeline.llm import Call, EnrichOut

OUT = dict(kid_friendly="no", kid_friendly_quote="21+ only", age_text="ages 21+", age_min=21, age_max=None,
           price="paid", price_quote="$20 suggested donation", price_text="$20 suggested donation",
           registration="yes", registration_quote="RSVP required", organizer_type="business",
           organizer_type_quote="902 Brewing", status="scheduled", status_quote=None, topics=["nightlife", "games"],
           summary="An adult spelling bee at a brewery.", venue_name="902 Brewing",
           venue_address="101 Pacific Ave, Jersey City, NJ 07304", venue_quote="101 Pacific Ave, Jersey City, NJ 07304")


def test_schema_is_strict():
    schema = EnrichOut.model_json_schema()
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])


def test_quotes_must_be_substrings(make_raw):
    raw = make_raw(title="Sip & Spell: Adult Spelling Bee", offsite=True,
                   description="Join us at 902 Brewing (101 Pacific Ave, Jersey City, NJ 07304). Ages 21+ only. "
                               "$20 suggested donation. RSVP required.")
    f = enrich.merge(raw, OUT)
    assert f["kid_friendly"] == "no" and f["evidence"]["kid_friendly"].quote == "21+ only"
    assert f["price"] == "paid" and f["price_text"] == "$20 suggested donation"
    assert f["registration"] == "yes" and f["organizer_type"] == "business"
    assert (f["age_text"], f["age_min"], f["age_max"]) == ("ages 21+", 21, None)
    assert f["venue_address"].startswith("101 Pacific Ave") and f["evidence"]["venue"].from_ == "model"
    assert f["topics"] == ["games", "nightlife"] and f["summary"].startswith("An adult")

    bad = dict(OUT, kid_friendly_quote="adults only", price_quote="twenty dollars", age_text="21 and over",
               venue_quote="somewhere else")
    g = enrich.merge(raw, bad)
    assert g["kid_friendly"] == "unknown" and "kid_friendly" not in g["evidence"]
    assert g["price"] == "unknown" and g["age_text"] is None and g["venue_address"] is None


def test_adapter_rules_win_and_no_model_is_fine(make_raw):
    raw = make_raw(kid_friendly="yes", price="free",
                   evidence={"kid_friendly": {"quote": "storytime events", "from": "categories"}},
                   description="21+ only. $20.")
    f = enrich.merge(raw, dict(OUT, status="cancelled", status_quote="cancelled"))
    assert f["kid_friendly"] == "yes" and f["price"] == "free" and f["status"] == "scheduled"
    assert enrich.merge(raw, None)["kid_friendly"] == "yes"


def test_enrich_all_caches_and_caps(make_raw, tmp_path):
    calls = []

    def fake(text):
        calls.append(text)
        return Call(input_hash="x", model="fake", out=OUT, cost_usd=0.6)

    raws = [make_raw(source_uid="1"), make_raw(source_uid="2", title="Other"), make_raw(source_uid="3", title="Third")]
    fields, stats = enrich.enrich_all(raws, fake, cap_usd=1.0, cache_path=tmp_path / "e.json")
    assert stats["calls"] == 2 and stats["stopped_at_cap"] and stats["no_model"] == 1
    assert fields["t:1"]["summary"] and fields["t:3"]["summary"] is None
    fields, stats = enrich.enrich_all(raws, fake, cap_usd=1.0, cache_path=tmp_path / "e.json")
    assert stats["cached"] == 2 and stats["calls"] == 1 and len(calls) == 3
    fields, stats = enrich.enrich_all(raws, None, cap_usd=1.0, cache_path=tmp_path / "e.json")
    assert stats["cached"] == 3 and stats["no_model"] == 0


def test_enrich_all_runs_chunks_concurrently(make_raw, tmp_path):
    calls = []

    def fake(text):
        calls.append(text)
        return Call(input_hash="x", model="fake", out=OUT, cost_usd=0.6)

    raws = [make_raw(source_uid=str(i), title=f"Event {i}") for i in range(5)]
    fields, stats = enrich.enrich_all(raws, fake, cap_usd=1.0, cache_path=tmp_path / "e.json", concurrency=3)
    assert stats["calls"] == 3 and stats["stopped_at_cap"] and stats["no_model"] == 2 and len(calls) == 3
    assert all(fields[f"t:{i}"]["summary"] for i in range(3)) and fields["t:4"]["summary"] is None


def test_organizer_type_model_first_then_source_default(make_raw):
    raw = make_raw(source_id="culture", description="An artist talk at SMUSH Gallery.")
    proved = enrich.merge(raw, dict(OUT, organizer_type="community", organizer_type_quote="SMUSH Gallery"), "city")
    assert proved["organizer_type"] == "community" and proved["evidence"]["organizer_type"].from_ == "model"
    unproved = enrich.merge(raw, dict(OUT, organizer_type="community", organizer_type_quote="nowhere"), "city")
    assert unproved["organizer_type"] == "city" and unproved["evidence"]["organizer_type"].quote == "source: culture"
    assert enrich.merge(raw, None, "city")["organizer_type"] == "city"
    assert enrich.merge(raw, None)["organizer_type"] == "unknown"


def test_cache_prunes_unused_entries(make_raw, tmp_path):
    import json
    from pipeline.util import sha
    raw = make_raw(source_uid="1")
    cache = {sha(raw.enrich_text()): {"out": OUT, "model": "fake", "at": "2026-08-01T00:00:00+00:00"},
             "deadbeef": {"out": OUT, "model": "fake", "at": "2026-01-01T00:00:00+00:00"},
             "recent": {"out": OUT, "model": "fake", "at": "2099-01-01T00:00:00+00:00"}}
    (tmp_path / "e.json").write_text(json.dumps(cache))
    fields, stats = enrich.enrich_all([raw], None, cap_usd=1.0, cache_path=tmp_path / "e.json")
    after = json.loads((tmp_path / "e.json").read_text())
    assert stats["pruned"] == 1 and "deadbeef" not in after and "recent" in after
    assert after[sha(raw.enrich_text())]["seen"] >= "2026-09-24" and fields["t:1"]["summary"]


def test_type_comes_from_the_title_then_the_feed_categories(make_raw):
    from pipeline.util import normalize

    def type_of(title, categories=()):
        raw = make_raw(title=title, categories=list(categories))
        kind, why = enrich.type_of(raw)
        assert why is None or normalize(why.quote) in normalize(raw.enrich_text())  # evidence, like any other field
        return kind, why and why.from_

    assert type_of("Hamilton Park Farmers Market 2026") == ("markets", "title")
    assert type_of("Egyptian Festival 2026") == ("festivals", "title")
    assert type_of("Bonetti Storytime") == ("stories", "title")
    assert type_of("NJ Symphony Arts & Music Festival Kids Day")[0] == "festivals"  # the order settles overlaps
    assert type_of("Musical Bingo for Adults")[0] == "games"
    assert type_of("History on the Hudson")[0] == "classes"  # "story" inside "History" is no story
    assert type_of("Community Business Academy: Start, Scale & Sustain")[0] == "classes"  # nor "art" inside "Start"
    assert type_of("SAT Diagnostic Tests Session")[0] == "classes" and type_of("Sat. Social")[0] == "unknown"
    assert type_of("Paper Architects", ["October", "Popular Events > Arts and Crafts Events"]) == ("crafts", "categories")
    assert type_of("Teen Advisory Board", ["Teen Programs"]) == ("unknown", None)
    f = enrich.merge(make_raw(title="Run Club"), None)
    assert f["type"] == "health" and f["evidence"]["type"].quote == "Run Club"
