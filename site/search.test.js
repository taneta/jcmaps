import { test } from "node:test";
import assert from "node:assert/strict";
import { fromLocal, windowFor, matches, search, localDateStr, listFor, pinCounts, pinIcons } from "./search.js";

const NOW = fromLocal(2026, 9, 24, 15, 0); // Thursday 3pm in Jersey City
const iso = (d) => d.toISOString();

test("wall clock to instant handles daylight saving", () => {
  assert.equal(iso(fromLocal(2026, 9, 24, 15, 0)), "2026-09-24T19:00:00.000Z"); // EDT, UTC-4
  assert.equal(iso(fromLocal(2026, 11, 1, 12, 0)), "2026-11-01T17:00:00.000Z"); // day clocks fall back: EST by noon
  assert.equal(iso(fromLocal(2026, 12, 15, 9, 0)), "2026-12-15T14:00:00.000Z"); // EST, UTC-5
  assert.equal(localDateStr(new Date("2026-09-25T02:30:00Z")), "2026-09-24");
});

test("named windows", () => {
  const w = (n, now = NOW) => windowFor(n, now);
  assert.deepEqual([iso(w("today").start), iso(w("today").end)], ["2026-09-24T19:00:00.000Z", "2026-09-25T04:00:00.000Z"]); // now to midnight
  const late = fromLocal(2026, 9, 24, 23, 30);
  assert.deepEqual([iso(w("today", late).start), iso(w("today", late).end)], ["2026-09-25T03:30:00.000Z", "2026-09-25T04:00:00.000Z"]);
  assert.deepEqual([iso(w("tomorrow").start), iso(w("tomorrow").end)], ["2026-09-25T04:00:00.000Z", "2026-09-26T04:00:00.000Z"]);
  assert.deepEqual([iso(w("weekend").start), iso(w("weekend").end)], ["2026-09-26T04:00:00.000Z", "2026-09-28T04:00:00.000Z"]);
  const sunday = fromLocal(2026, 9, 27, 10, 0);
  assert.deepEqual([iso(w("weekend", sunday).start), iso(w("weekend", sunday).end)], ["2026-09-27T14:00:00.000Z", "2026-09-28T04:00:00.000Z"]);
  const saturday = fromLocal(2026, 9, 26, 8, 0);
  assert.equal(iso(w("weekend", saturday).start), "2026-09-26T12:00:00.000Z"); // clamped to now
});

test("occurrence matching: today drops what is over and keeps what is under way or all day", () => {
  const today = windowFor("today", NOW); // Thursday, 3pm to midnight
  const occ = (start, end, all_day = false, date = "2026-09-24") => ({ start_utc: start, end_utc: end, all_day, date });
  assert.ok(!matches(occ("2026-09-24T14:00:00Z", "2026-09-24T16:00:00Z"), today)); // 10am-noon: ended earlier today
  assert.ok(matches(occ("2026-09-24T18:00:00Z", "2026-09-24T20:00:00Z"), today)); // 2-4pm: under way
  assert.ok(matches(occ("2026-09-24T17:30:00Z", null), today)); // 1:30pm, no end: two hours reach past 3pm
  assert.ok(!matches(occ("2026-09-24T16:00:00Z", null), today)); // noon, no end: over by 2pm
  assert.ok(matches(occ("2026-09-24T23:00:00Z", null), today)); // 7pm
  assert.ok(matches(occ("2026-09-24T04:00:00Z", "2026-09-25T04:00:00Z", true), today)); // all day today
  assert.ok(!matches(occ("2026-09-25T13:00:00Z", "2026-09-25T14:00:00Z", false, "2026-09-25"), today)); // tomorrow, 9am
  const weekend = windowFor("weekend", NOW);
  assert.ok(matches(occ("2026-09-26T04:00:00Z", "2026-09-27T04:00:00Z", true, "2026-09-26"), weekend));
  assert.ok(!matches(occ("2026-09-25T04:00:00Z", "2026-09-26T04:00:00Z", true, "2026-09-25"), weekend));
});

const SNAP = {
  city: { tz: "America/New_York" },
  venues: [{ id: "v", name: "Main", lat: 40.7, lon: -74.05 }],
  events: [
    { id: "a", title: "Storytime", kid_friendly: "yes", price: "free", status: "scheduled", ongoing: false, age_min: 3, age_max: 5 },
    { id: "b", title: "Mixer", kid_friendly: "no", price: "paid", status: "scheduled", ongoing: false, age_min: null, age_max: null },
    { id: "c", title: "Exhibit", kid_friendly: "unknown", price: "unknown", status: "scheduled", ongoing: true, age_min: null, age_max: null },
    { id: "d", title: "Cancelled thing", kid_friendly: "yes", price: "free", status: "cancelled", ongoing: false, age_min: null, age_max: null },
    { id: "e", title: "Open studio", kid_friendly: "yes", price: "unknown", status: "scheduled", ongoing: false, age_min: null, age_max: null },
  ],
  occurrences: [
    { event_id: "a", venue_id: "v", start_utc: "2026-09-26T14:00:00Z", end_utc: "2026-09-26T15:00:00Z", all_day: false, date: "2026-09-26" },
    { event_id: "b", venue_id: "v", start_utc: "2026-09-26T23:00:00Z", end_utc: null, all_day: false, date: "2026-09-26" },
    { event_id: "c", venue_id: null, start_utc: "2026-09-10T04:00:00Z", end_utc: "2026-10-10T04:00:00Z", all_day: false, date: "2026-09-10" },
    { event_id: "d", venue_id: "v", start_utc: "2026-09-26T16:00:00Z", end_utc: null, all_day: false, date: "2026-09-26" },
    { event_id: "e", venue_id: "v", start_utc: "2026-09-26T18:00:00Z", end_utc: null, all_day: false, date: "2026-09-26" },
  ],
};

test("filters: view, free, cancelled, ongoing layer, labels", () => {
  const ids = (r) => r.results.map((x) => x.event.id);
  const family = search(SNAP, { window: "weekend", view: "family" }, NOW);
  assert.deepEqual(ids(family), ["a", "e"]);
  assert.deepEqual(family.ongoing.map((x) => x.event.id), ["c"]);
  assert.deepEqual(family.ongoing[0].labels, ["kids: not stated", "price not listed"]);
  assert.deepEqual(family.unlisted, []); // only Free leaves events out for their price
  assert.deepEqual(ids(search(SNAP, { window: "weekend", view: "everyone" }, NOW)), ["a", "e", "b"]);
  assert.equal(family.results[0].venue.name, "Main");
});

test("free: only events that say they are free, and a count of those left out for not listing a price", () => {
  const free = search(SNAP, { window: "weekend", view: "everyone", freeOnly: true }, NOW);
  assert.deepEqual(free.results.map((x) => x.event.id), ["a"]);
  assert.deepEqual(free.ongoing, []);
  assert.deepEqual(free.unlisted.map((x) => x.event.id).sort(), ["c", "e"]); // the paid mixer is not counted
  const { inView, unpinned } = listFor(free.unlisted, null); // the list counts them where it lists events
  assert.equal(inView.length + unpinned.length, 2);
});

// Issue #2: one pin on a street-level screen, two events without a pin, one pin off screen.
const venue = (id, lat, lon) => ({ id, name: id, lat, lon });
const branch = venue("branch", 40.7122, -74.0566), park = venue("park", 40.745, -74.03), nowhere = venue("nowhere", null, null);
const item = (id, v) => ({ event: { id }, venue: v });
const ITEMS = [item("1", branch), item("2", park), item("3", branch), item("4", nowhere), item("5", null)];
const STREET = [[-74.06, 40.71], [-74.05, 40.715]]; // [[west, south], [east, north]] around the branch only
const ids = (items) => items.map((i) => i.event.id);

test("list: the header counts pinned events in view; events without a pin are listed apart", () => {
  const list = listFor(ITEMS, STREET);
  assert.deepEqual(ids(list.inView), ["1", "3"]); // two, not four: the unpinned events are not in view
  assert.deepEqual(ids(list.unpinned), ["4", "5"]);
  assert.deepEqual(ids(listFor(ITEMS, null).inView), ["1", "2", "3"]); // no map: every pinned event
});

test("list: a tapped pin lists exactly as many events as its label", () => {
  const counts = pinCounts(ITEMS);
  assert.deepEqual([...counts], [["branch", 2], ["park", 1]]);
  for (const [id, n] of counts) {
    const list = listFor(ITEMS, STREET, id); // bounds do not count once a pin is tapped: its centre may be just off screen
    assert.equal(list.inView.length, n);
    assert.ok(list.inView.every((i) => i.venue.id === id));
    assert.deepEqual(list.unpinned, []);
  }
});

test("pins: the icon is the type the events share; several types show the place's icon, or several", () => {
  const lib = { id: "lib", kind: "library", lat: 40.71, lon: -74.05 }, hall = { id: "hall", kind: null, lat: 40.72, lon: -74.04 };
  const park = venue("park", 40.73, -74.03), cafe = venue("cafe", 40.74, -74.02);
  const at = (v, type) => ({ event: { type }, venue: v });
  const places = new Set(["library"]);
  const one = pinIcons([at(lib, "stories"), at(lib, "stories"), at(hall, "shows"), at(hall, "unknown"), at(nowhere, "music")], places);
  assert.deepEqual(Object.fromEntries(one), { lib: "stories", hall: "shows" }); // unknown does not make a mix
  const several = pinIcons([at(lib, "stories"), at(lib, "crafts"), at(park, "markets"), at(park, "health"), at(cafe, "unknown")], places);
  assert.deepEqual(Object.fromEntries(several), { lib: "library", park: "several", cafe: null });
});
