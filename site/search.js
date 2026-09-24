// Search rules over the snapshot. Pure functions, no DOM: the browser and `node --test` both import this file.
export const TZ = "America/New_York";
const HOUR = 3600e3;
const DEFAULT_LENGTH = 2 * HOUR;
const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

// Wall-clock parts of an instant in the city's time zone.
export function localParts(date, tz = TZ) {
  const f = new Intl.DateTimeFormat("en-US", { timeZone: tz, hourCycle: "h23", year: "numeric", month: "2-digit",
    day: "2-digit", hour: "2-digit", minute: "2-digit", weekday: "short" });
  const p = Object.fromEntries(f.formatToParts(date).map((x) => [x.type, x.value]));
  return { y: +p.year, m: +p.month, d: +p.day, h: +p.hour % 24, min: +p.minute, wd: WEEKDAYS.indexOf(p.weekday) };
}

// The instant of a wall-clock time in the city's time zone (handles daylight saving by correction).
export function fromLocal(y, m, d, h = 0, min = 0, tz = TZ) {
  const wanted = Date.UTC(y, m - 1, d, h, min);
  let guess = wanted;
  for (let i = 0; i < 2; i++) {
    const p = localParts(new Date(guess), tz);
    guess += wanted - Date.UTC(p.y, p.m - 1, p.d, p.h, p.min);
  }
  return new Date(guess);
}

export function localDateStr(date, tz = TZ) {
  const p = localParts(date, tz);
  return `${p.y}-${String(p.m).padStart(2, "0")}-${String(p.d).padStart(2, "0")}`;
}

const addDays = (p, n) => new Date(Date.UTC(p.y, p.m - 1, p.d + n, 12));

// Named windows. Afternoon and Evening move to the next day once today's has passed.
export function windowFor(name, now, tz = TZ) {
  const p = localParts(now, tz);
  const dayAt = (offset, h1, h2) => {
    const q = localParts(addDays(p, offset), "UTC");
    return { start: fromLocal(q.y, q.m, q.d, h1, 0, tz), end: fromLocal(q.y, q.m, q.d, h2, 0, tz) };
  };
  switch (name) {
    case "now":
      return { start: now, end: new Date(now.getTime() + 3 * HOUR) };
    case "afternoon": {
      const w = dayAt(0, 12, 17);
      return now < w.end ? w : dayAt(1, 12, 17);
    }
    case "evening": {
      const w = dayAt(0, 17, 21);
      return now < w.end ? w : dayAt(1, 17, 21);
    }
    case "tomorrow":
      return dayAt(1, 0, 24);
    case "weekend": {
      const toSat = (6 - p.wd + 7) % 7;
      const sat = p.wd === 0 ? -1 : toSat; // on Sunday the weekend started yesterday
      const w = { start: dayAt(sat, 0, 24).start, end: dayAt(sat + 2, 0, 24).start };
      return { start: new Date(Math.max(w.start, now)), end: w.end };
    }
    default:
      throw new Error(`unknown window ${name}`);
  }
}

// An occurrence matches if it starts before the window ends and ends after it starts.
// A missing end means two hours. All-day items match any window touching their date.
export function matches(occ, win, tz = TZ) {
  if (occ.all_day) {
    const first = localDateStr(win.start, tz);
    const last = localDateStr(new Date(win.end.getTime() - 1), tz);
    return occ.date >= first && occ.date <= last;
  }
  const s = Date.parse(occ.start_utc);
  const e = occ.end_utc ? Date.parse(occ.end_utc) : s + DEFAULT_LENGTH;
  return s < win.end.getTime() && e > win.start.getTime();
}

export function ageMatches(ev, age) {
  if (ev.age_min == null && ev.age_max == null) return true; // unknown range: shown, with a label
  if (ev.age_min != null && age < ev.age_min) return false;
  return !(ev.age_max != null && age > ev.age_max);
}

export function labelsFor(ev, filter) {
  const labels = [];
  if (ev.kid_friendly === "unknown") labels.push("kids: not stated");
  if (ev.price === "unknown") labels.push("price not listed");
  if (filter.childAge != null && ev.age_min == null && ev.age_max == null) labels.push("ages not stated");
  return labels;
}

// filter: { window: name | {start, end}, view: "family" | "everyone", freeOnly, childAge }
export function search(snapshot, filter, now = new Date()) {
  const tz = snapshot.city?.tz || TZ;
  const win = typeof filter.window === "string" ? windowFor(filter.window, now, tz) : filter.window;
  const events = new Map(snapshot.events.map((e) => [e.id, e]));
  const venues = new Map(snapshot.venues.map((v) => [v.id, v]));
  const results = [];
  const ongoing = [];
  for (const occ of snapshot.occurrences) {
    const ev = events.get(occ.event_id);
    if (!ev || ev.status === "cancelled") continue;
    if (filter.view !== "everyone" && ev.kid_friendly === "no") continue;
    if (filter.freeOnly && ev.price !== "free") continue;
    if (filter.childAge != null && !ageMatches(ev, filter.childAge)) continue;
    if (!matches(occ, win, tz)) continue;
    const item = { event: ev, occ, venue: venues.get(occ.venue_id) || null, labels: labelsFor(ev, filter) };
    (ev.ongoing ? ongoing : results).push(item);
  }
  const byStart = (a, b) => Date.parse(a.occ.start_utc) - Date.parse(b.occ.start_utc);
  return { window: win, results: results.sort(byStart), ongoing: ongoing.sort(byStart) };
}

const pinned = (item) => item.venue != null && item.venue.lat != null;

// The number on each pin: items per venue with coordinates.
export function pinCounts(items) {
  const counts = new Map();
  for (const i of items) if (pinned(i)) counts.set(i.venue.id, (counts.get(i.venue.id) || 0) + 1);
  return counts;
}

// The list under the map: items whose pin is inside bounds ([[west, south], [east, north]]; null means no map),
// or, after a pin is tapped, that venue's items, since its pin is on screen. Items without a pin cannot be in view,
// so they are listed apart, and not at all while a pin is tapped.
export function listFor(items, bounds, venueId = null) {
  const inView = [], unpinned = [];
  for (const i of items) {
    if (!pinned(i)) {
      if (!venueId) unpinned.push(i);
      continue;
    }
    const { id, lat, lon } = i.venue;
    const shown = venueId ? id === venueId
      : !bounds || (lon >= bounds[0][0] && lon <= bounds[1][0] && lat >= bounds[0][1] && lat <= bounds[1][1]);
    if (shown) inView.push(i);
  }
  return { inView, unpinned };
}
