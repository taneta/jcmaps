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
  assert.deepEqual([iso(w("now").start), iso(w("now").end)], ["2026-09-24T19:00:00.000Z", "2026-09-24T22:00:00.000Z"]);
  assert.deepEqual([iso(w("afternoon").start), iso(w("afternoon").end)], ["2026-09-24T16:00:00.000Z", "2026-09-24T21:00:00.000Z"]);
  assert.deepEqual([iso(w("evening").start), iso(w("evening").end)], ["2026-09-24T21:00:00.000Z", "2026-09-25T01:00:00.000Z"]);
  const late = fromLocal(2026, 9, 24, 21, 30);
  assert.equal(iso(w("afternoon", late).start), "2026-09-25T16:00:00.000Z"); // today's afternoon is over
  assert.equal(iso(w("evening", late).start), "2026-09-25T21:00:00.000Z");
  assert.deepEqual([iso(w("tomorrow").start), iso(w("tomorrow").end)], ["2026-09-25T04:00:00.000Z", "2026-09-26T04:00:00.000Z"]);
  assert.deepEqual([iso(w("weekend").start), iso(w("weekend").end)], ["2026-09-26T04:00:00.000Z", "2026-09-28T04:00:00.000Z"]);
  const sunday = fromLocal(2026, 9, 27, 10, 0);
  assert.deepEqual([iso(w("weekend", sunday).start), iso(w("weekend", sunday).end)], ["2026-09-27T14:00:00.000Z", "2026-09-28T04:00:00.000Z"]);
  const saturday = fromLocal(2026, 9, 26, 8, 0);
  assert.equal(iso(w("weekend", saturday).start), "2026-09-26T12:00:00.000Z"); // clamped to now
});

test("occurrence matching", () => {
  const afternoon = windowFor("afternoon", NOW);
  const occ = (start, end, all_day = false, date = "2026-09-24") => ({ start_utc: start, end_utc: end, all_day, date });
  assert.ok(matches(occ("2026-09-24T20:30:00Z", "2026-09-24T21:30:00Z"), afternoon)); // 4:30-5:30pm overlaps
  assert.ok(!matches(occ("2026-09-24T21:00:00Z", "2026-09-24T22:00:00Z"), afternoon)); // starts at 5pm sharp
  assert.ok(matches(occ("2026-09-24T15:00:00Z", null), afternoon)); // 11am, no end: two hours reach into the afternoon
  assert.ok(!matches(occ("2026-09-24T13:30:00Z", null), afternoon));
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
  ],
  occurrences: [
    { event_id: "a", venue_id: "v", start_utc: "2026-09-26T14:00:00Z", end_utc: "2026-09-26T15:00:00Z", all_day: false, date: "2026-09-26" },
    { event_id: "b", venue_id: "v", start_utc: "2026-09-26T23:00:00Z", end_utc: null, all_day: false, date: "2026-09-26" },
    { event_id: "c", venue_id: null, start_utc: "2026-09-10T04:00:00Z", end_utc: "2026-10-10T04:00:00Z", all_day: false, date: "2026-09-10" },
    { event_id: "d", venue_id: "v", start_utc: "2026-09-26T16:00:00Z", end_utc: null, all_day: false, date: "2026-09-26" },
  ],
};

test("filters: view, free, age, cancelled, ongoing layer, labels", () => {
  const ids = (r) => r.results.map((x) => x.event.id);
  const family = search(SNAP, { window: "weekend", view: "family" }, NOW);
  assert.deepEqual(ids(family), ["a"]);
  assert.deepEqual(family.ongoing.map((x) => x.event.id), ["c"]);
  assert.deepEqual(family.ongoing[0].labels, ["kids: not stated", "price not listed"]);
  assert.deepEqual(ids(search(SNAP, { window: "weekend", view: "everyone" }, NOW)), ["a", "b"]);
  assert.deepEqual(ids(search(SNAP, { window: "weekend", view: "everyone", freeOnly: true }, NOW)), ["a"]);
  assert.deepEqual(ids(search(SNAP, { window: "weekend", view: "everyone", childAge: 9 }, NOW)), ["b"]);
  const aged = search(SNAP, { window: "weekend", view: "everyone", childAge: 4 }, NOW);
  assert.deepEqual(ids(aged), ["a", "b"]);
  assert.deepEqual(aged.results[1].labels, ["ages not stated"]);
  assert.equal(family.results[0].venue.name, "Main");
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
