import { search, fromLocal, localParts, listFor, pinCounts, pinIcons, WINDOWS } from "./search.js";
import { ICONS, PLACES, TYPES } from "./icons.js";

const REPO = "taneta/jcmaps"; // "Report a problem" opens a prefilled issue here
const DATA = "data/events.json";
const $ = (s) => document.querySelector(s);
// Colors are the CSS tokens in tokens.css (docs/design.md); the map reads them, so it follows the theme.
const token = (name) => getComputedStyle(document.documentElement).getPropertyValue("--" + name).trim();

const state = { window: "today", view: "family", freeOnly: false, venue: null, custom: null };
let snapshot = null, map = null, current = null, selected = null;

// ---- URL state, so a link can carry a filter ("tomorrow, free") ----
function readHash() {
  const p = new URLSearchParams(location.hash.slice(1));
  if (p.get("v") === "everyone") state.view = "everyone";
  state.freeOnly = p.get("free") === "1";
  if (p.get("from") && p.get("to")) state.custom = { from: p.get("from"), to: p.get("to") };
  // An old link (w=now, afternoon, evening) or a window without dates opens on Today; age= is ignored.
  const w = p.get("w");
  state.window = WINDOWS.includes(w) || (w === "custom" && state.custom) ? w : "today";
}
function writeHash() {
  const p = new URLSearchParams();
  p.set("w", state.window);
  if (state.view === "everyone") p.set("v", "everyone");
  if (state.freeOnly) p.set("free", "1");
  if (state.window === "custom" && state.custom) { p.set("from", state.custom.from); p.set("to", state.custom.to); }
  history.replaceState(null, "", "#" + p.toString());
}

// ---- formatting ----
const tz = () => snapshot?.city?.tz || "America/New_York";
const fmtDay = (d) => new Intl.DateTimeFormat("en-US", { timeZone: tz(), weekday: "short", month: "short", day: "numeric" }).format(d);
const fmtTime = (d) => new Intl.DateTimeFormat("en-US", { timeZone: tz(), hour: "numeric", minute: "2-digit" }).format(d).replace(":00", "");
function when(occ) {
  const s = new Date(occ.start_utc);
  if (occ.all_day) return [fmtDay(s), "all day"];
  let t = fmtTime(s);
  if (occ.end_utc) {
    const e = fmtTime(new Date(occ.end_utc));
    t = t.slice(-2) === e.slice(-2) ? `${t.slice(0, -3)}–${e}` : `${t}–${e}`; // "3:30–4:15 PM", but "11:30 AM–12:45 PM"
  }
  return [fmtDay(s), t]; // the day and the time, each kept whole on the card
}
function customWindow() {
  const { from, to } = state.custom;
  const [y1, m1, d1] = from.split("-").map(Number), [y2, m2, d2] = to.split("-").map(Number);
  return { start: fromLocal(y1, m1, d1), end: fromLocal(y2, m2, d2 + 1) };
}
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function reportUrl(ev) {
  const title = `Wrong listing: ${ev.title}`.slice(0, 120);
  const body = `**Where:** data · **Seen:** live site, ${new Date().toISOString().slice(0, 10)}\n\nEvent: ${ev.title}\nId: ${ev.id}\nSource: ${ev.url}\n\n## What happens\n(What is wrong: the time, the place, it is cancelled, not for kids, the price, something else?)\n\n## What should happen\n\n`;
  return `https://github.com/${REPO}/issues/new?labels=report&title=${encodeURIComponent(title)}&body=${encodeURIComponent(body)}`;
}

// ---- rendering ----
const glyph = (name) => `<svg viewBox="0 0 256 256" aria-hidden="true"><path d="${ICONS[name]}"/></svg>`;

function card(item) {
  const { event: ev, occ, venue, labels } = item;
  const type = TYPES[ev.type]; // the icon and its name lead the card, so a list can be read by kind (docs/design.md, Icons)
  const tags = [];
  if (ev.price === "free") tags.push('<span class="tag free">Free</span>');
  else if (ev.price === "paid") tags.push(`<span class="tag">${esc(ev.price_text || "Paid")}</span>`);
  if (ev.kid_friendly === "yes") tags.push('<span class="tag kids">Kids</span>');
  if (ev.age_text) tags.push(`<span class="tag">${esc(ev.age_text)}</span>`);
  if (ev.registration === "yes") tags.push('<span class="tag">Registration</span>');
  for (const l of labels) tags.push(`<span class="tag unknown">${esc(l)}</span>`);
  const where = venue ? venue.name : "Location not stated";
  const [day, time] = when(occ);
  return `<div class="card${selected === ev.id ? " sel" : ""}" data-id="${esc(ev.id)}" data-venue="${esc(occ.venue_id || "")}">
    <div class="when"><span class="mark">${type ? glyph(ev.type) : ""}</span><span>${type ? `<span>${esc(type)}</span> · ` : ""}<span>${esc(day)}</span> · <span>${esc(time)}</span></span></div>
    <h3>${esc(ev.title)}</h3>
    <div class="where">${esc(where)}${ev.organizer_name && ev.source_id !== "library" ? " · " + esc(ev.organizer_name) : ""}</div>
    ${ev.summary ? `<div class="sum">${esc(ev.summary)}</div>` : ""}
    <div class="tags">${tags.join("")}</div>
    <div class="links"><a href="${esc(ev.url)}" target="_blank" rel="noopener">Source ↗</a><a href="${reportUrl(ev)}" target="_blank" rel="noopener">Report a problem</a></div>
  </div>`;
}

function render() {
  if (!snapshot) return;
  const filter = { window: state.window === "custom" ? customWindow() : state.window, view: state.view, freeOnly: state.freeOnly };
  current = search(snapshot, filter, new Date());
  const all = current.results.concat(current.ongoing);
  const counts = pinCounts(all), icons = pinIcons(all, new Set(Object.keys(PLACES)));
  if (!counts.has(state.venue)) state.venue = null; // a filter took the tapped pin off the map
  const bounds = map ? map.getBounds().toArray() : null;
  const { inView, unpinned } = listFor(all, bounds, state.venue);
  // Free leaves out events that do not list a price; the list says how many, counted where it lists events.
  const left = state.freeOnly ? listFor(current.unlisted, bounds, state.venue) : { inView: [], unpinned: [] };
  const leftOut = left.inView.length + left.unpinned.length;
  const ongoing = inView.filter((i) => i.event.ongoing);
  const venueName = state.venue && snapshot.venues.find((v) => v.id === state.venue)?.name;
  $("#count").textContent = `${inView.length} event${inView.length === 1 ? "" : "s"}${venueName ? " at " + venueName : " in view"}`;
  $("#hint").textContent = state.venue || all.length === inView.length ? "" : `${all.length} total`;
  $("#clear").hidden = !state.venue;
  let html = inView.filter((i) => !i.event.ongoing).map(card).join("");
  if (!inView.length) html = `<div class="empty">Nothing on the map here for this window. Try another time, zoom out, or switch to Everyone.</div>`;
  if (leftOut) html = `<div class="note">${leftOut} more ${leftOut === 1 ? "doesn't" : "don't"} list a price</div>` + html;
  if (ongoing.length) html += `<div class="section">Ongoing (${ongoing.length})</div>` + ongoing.map(card).join("");
  if (unpinned.length) html += `<div class="section">No map pin (${unpinned.length})</div>` + unpinned.map(card).join("");
  const gen = new Date(snapshot.generated_at);
  html += `<div class="foot">Updated ${fmtDay(gen)} ${fmtTime(gen)} · ${snapshot.events.length} events from ${Object.keys(snapshot.sources).length} sources · Times in Jersey City time. <a href="about.html">About JC Maps</a></div>`;
  $("#list").innerHTML = html;
  updatePins(counts, icons);
  writeHash();
}

function updatePins(counts, icons) {
  if (!map || !map.getSource("venues")) return;
  const features = snapshot.venues.filter((v) => counts.has(v.id)).map((v) => ({
    type: "Feature", geometry: { type: "Point", coordinates: [v.lon, v.lat] },
    properties: { id: v.id, name: v.name, count: counts.get(v.id), icon: icons.get(v.id) || "", sel: v.id === state.venue ? 1 : 0 } }));
  map.getSource("venues").setData({ type: "FeatureCollection", features });
}

// ---- controls ----
function syncControls() {
  for (const b of document.querySelectorAll("#windows .chip")) b.setAttribute("aria-pressed", String(b.dataset.w === state.window));
  $('#windows [aria-pressed="true"]')?.scrollIntoView({ block: "nearest", inline: "nearest" }); // on a phone the row scrolls
  $("#dates").classList.toggle("on", state.window === "custom");
  for (const b of document.querySelectorAll("#view button")) b.setAttribute("aria-pressed", String(b.dataset.v === state.view));
  $("#free").setAttribute("aria-pressed", String(state.freeOnly));
  if (state.custom) { $("#d1").value = state.custom.from; $("#d2").value = state.custom.to; }
}

function wire() {
  $("#windows").addEventListener("click", (e) => {
    const b = e.target.closest("[data-w]"); if (!b) return;
    state.window = b.dataset.w;
    if (state.window === "custom" && !state.custom) {
      const p = localParts(new Date(), tz()); const iso = (d) => new Date(Date.UTC(p.y, p.m - 1, p.d + d)).toISOString().slice(0, 10);
      state.custom = { from: iso(0), to: iso(6) };
    }
    syncControls(); render();
  });
  const dateChange = () => {
    const from = $("#d1").value, to = $("#d2").value;
    if (from && to && to >= from) { state.custom = { from, to }; render(); }
  };
  $("#d1").addEventListener("change", dateChange); $("#d2").addEventListener("change", dateChange);
  $("#view").addEventListener("click", (e) => {
    const b = e.target.closest("[data-v]"); if (!b) return;
    state.view = b.dataset.v; syncControls(); render();
  });
  $("#free").addEventListener("click", () => { state.freeOnly = !state.freeOnly; syncControls(); render(); });
  // The sheet follows a finger on its handle and settles at peek, half or full (the heights in the CSS). A pointer
  // that hardly moved is a tap, which toggles half and full as before.
  const sheet = $("#sheet"), handle = $("#handle");
  let drag = null;
  handle.addEventListener("pointerdown", (e) => {
    if (e.target.closest("#clear")) return;
    drag = { y: e.clientY, height: sheet.offsetHeight, moved: false };
    handle.setPointerCapture(e.pointerId);
  });
  handle.addEventListener("pointermove", (e) => {
    if (!drag || (!drag.moved && Math.abs(e.clientY - drag.y) < 8)) return;
    drag.moved = true;
    sheet.classList.add("dragging");
    sheet.style.height = `${drag.height + drag.y - e.clientY}px`;
  });
  handle.addEventListener("pointerup", () => {
    if (!drag) return;
    const c = sheet.classList, stops = { peek: 64, half: innerHeight * 0.42, full: innerHeight * 0.88 };
    let to = c.contains("full") || c.contains("peek") ? "half" : "full";
    if (drag.moved) to = Object.keys(stops).reduce((a, b) => Math.abs(stops[b] - sheet.offsetHeight) < Math.abs(stops[a] - sheet.offsetHeight) ? b : a);
    c.remove("dragging"); sheet.style.height = "";
    c.toggle("peek", to === "peek"); c.toggle("full", to === "full");
    drag = null;
  });
  handle.addEventListener("pointercancel", () => { sheet.classList.remove("dragging"); sheet.style.height = ""; drag = null; });
  $("#clear").addEventListener("click", (e) => { e.stopPropagation(); state.venue = null; render(); });
  $("#list").addEventListener("click", (e) => {
    if (e.target.closest("a")) return;
    const c = e.target.closest(".card"); if (!c) return;
    selected = c.dataset.id;
    const v = snapshot.venues.find((x) => x.id === c.dataset.venue);
    // a tapped pin is already on screen, and moving the map would clear it
    if (!state.venue && v && v.lat != null && map) map.flyTo({ center: [v.lon, v.lat], zoom: Math.max(map.getZoom(), 14.5) });
    for (const el of document.querySelectorAll(".card")) el.classList.toggle("sel", el.dataset.id === selected);
  });
}

// ---- map ----
// The stock basemap is grey: paint land, water, parks, buildings and place names with the palette, whatever the
// layer ids, and hide route-number shields, which compete with the pins.
function tintBasemap() {
  const prop = { background: "background-color", fill: "fill-color", symbol: "text-color" };
  for (const l of map.getStyle().layers) {
    const src = l["source-layer"];
    if (l.id.includes("shield")) { map.setLayoutProperty(l.id, "visibility", "none"); continue; }
    const name = l.type === "background" ? "map-land" : l.type === "symbol" ? (src === "place" ? "ink-3" : null) : l.type !== "fill" ? null
      : src === "water" ? "map-water" : src === "building" ? "map-building" : /park|wood|grass/.test(l.id) ? "map-park"
      : ["landuse", "landcover", "transportation"].includes(src) ? "map-land" : null;
    if (name) map.setPaintProperty(l.id, prop[l.type], token(name));
  }
}

// The icons become map images once, painted with --on-accent; a pin shows its icon at 16px, 20px when selected.
function addIcons() {
  const ratio = Math.max(2, Math.ceil(devicePixelRatio || 1)), px = 20 * ratio, paint = token("on-accent");
  for (const [name, d] of Object.entries(ICONS)) {
    const g = Object.assign(document.createElement("canvas"), { width: px, height: px }).getContext("2d");
    g.scale(px / 256, px / 256);
    g.fillStyle = paint;
    g.fill(new Path2D(d));
    map.addImage("icon-" + name, g.getImageData(0, 0, px, px), { pixelRatio: ratio });
  }
}

function initMap() {
  const c = snapshot.city;
  map = new maplibregl.Map({ container: "map", style: "https://tiles.openfreemap.org/styles/positron", center: c.center, zoom: 12.4,
    maxBounds: [[c.bbox[0] - 0.12, c.bbox[1] - 0.08], [c.bbox[2] + 0.12, c.bbox[3] + 0.08]], attributionControl: false,
    dragRotate: false, maxPitch: 0 }); // north-up and flat: nothing to undo, and "in view" is what the screen shows
  map.touchZoomRotate.disableRotation();
  map.keyboard.disableRotation();
  // Our own credits line (docs/design.md), added first so it sits under the other controls: the two credits the map's
  // licenses ask for, written here rather than taken from the style, so a new basemap source needs its credit added.
  // They show when the map opens and fold behind ⓘ at the first pan, zoom or tap, as OpenStreetMap's guidelines allow.
  const credits = Object.assign(document.createElement("div"), { className: "maplibregl-ctrl credits", innerHTML:
    '<a href="about.html">About JC Maps</a><span class="licenses"> · <a href="https://openmaptiles.org/" target="_blank" rel="noopener">© OpenMapTiles</a> · ' +
    '<a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">© OpenStreetMap</a></span>' +
    '<button type="button" aria-label="Map credits" aria-expanded="true">ⓘ</button>' });
  const fold = (folded) => { credits.classList.toggle("folded", folded); credits.querySelector("button").setAttribute("aria-expanded", String(!folded)); };
  credits.querySelector("button").addEventListener("click", () => fold(!credits.classList.contains("folded")));
  for (const first of ["movestart", "click"]) map.once(first, () => fold(true));
  map.addControl({ onAdd: () => credits, onRemove: () => credits.remove() }, "bottom-right");
  if (matchMedia("(pointer: fine)").matches) map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right"); // phones pinch
  map.addControl(new maplibregl.GeolocateControl({ positionOptions: { enableHighAccuracy: true }, trackUserLocation: false }), "bottom-right");
  map.on("load", () => {
    tintBasemap();
    addIcons();
    const [accent, edge, onAccent, surface, ink] = ["accent", "accent-edge", "on-accent", "surface", "ink"].map(token);
    const n = ["coalesce", ["get", "count"], 0], sel = ["==", ["coalesce", ["get", "sel"], 0], 1], pin = ["!", ["has", "point_count"]];
    const pinRadius = ["case", sel, 18, 14]; // one size, since the icon fills the middle and the count has its own badge
    const ring = { "circle-color": accent, "circle-stroke-color": edge, "circle-stroke-width": 1.5 }; // yellow needs an edge on the light map
    const count = { "text-field": ["to-string", ["get", "count"]], "text-font": ["Noto Sans Bold"], "text-allow-overlap": true }; // OpenFreeMap's glyphs
    const corner = [11, -11]; // the count badge sits on the pin's top-right edge
    map.addSource("venues", { type: "geojson", data: { type: "FeatureCollection", features: [] }, cluster: true, clusterRadius: 36, clusterMaxZoom: 14,
      clusterProperties: { count: ["+", ["get", "count"]] } });
    // A selected pin is highlighted, never recolored: it grows and glows.
    map.addLayer({ id: "glow", type: "circle", source: "venues", filter: ["all", pin, sel],
      paint: { "circle-color": accent, "circle-opacity": 0.8, "circle-blur": 0.5, "circle-radius": ["+", pinRadius, 16] } });
    map.addLayer({ id: "clusters", type: "circle", source: "venues", filter: ["has", "point_count"],
      paint: { ...ring, "circle-radius": ["step", n, 16, 10, 20, 40, 25] } });
    map.addLayer({ id: "cluster-count", type: "symbol", source: "venues", filter: ["has", "point_count"],
      layout: { ...count, "text-size": 13 }, paint: { "text-color": onAccent } });
    map.addLayer({ id: "pins", type: "circle", source: "venues", filter: pin,
      paint: { ...ring, "circle-radius": pinRadius, "circle-stroke-width": ["case", sel, 2.5, 1.5] } });
    map.addLayer({ id: "pin-icons", type: "symbol", source: "venues", filter: ["all", pin, ["!=", ["get", "icon"], ""]],
      layout: { "icon-image": ["concat", "icon-", ["get", "icon"]], "icon-size": ["case", sel, 1, 0.8], "icon-allow-overlap": true, "icon-ignore-placement": true } });
    map.addLayer({ id: "pin-badges", type: "circle", source: "venues", filter: ["all", pin, [">", n, 1]],
      paint: { "circle-radius": 8.5, "circle-color": surface, "circle-stroke-color": edge, "circle-stroke-width": 1, "circle-translate": corner } });
    map.addLayer({ id: "pin-count", type: "symbol", source: "venues", filter: ["all", pin, [">", n, 1]],
      layout: { ...count, "text-size": 11 }, paint: { "text-color": ink, "text-translate": corner } });
    const tappable = ["pins", "pin-badges"];
    map.on("click", "clusters", (e) => {
      const f = map.queryRenderedFeatures(e.point, { layers: ["clusters"] })[0];
      map.getSource("venues").getClusterExpansionZoom(f.properties.cluster_id).then((z) => map.easeTo({ center: f.geometry.coordinates, zoom: z }));
    });
    map.on("click", tappable, (e) => {
      const f = e.features[0];
      state.venue = state.venue === f.properties.id ? null : f.properties.id;
      $("#sheet").classList.remove("peek");
      render();
    });
    for (const l of ["clusters", ...tappable]) { map.on("mouseenter", l, () => (map.getCanvas().style.cursor = "pointer")); map.on("mouseleave", l, () => (map.getCanvas().style.cursor = "")); }
    // A tapped pin holds the list until any drag, zoom or tap on empty map; then the list follows the viewport again.
    map.on("click", (e) => {
      if (state.venue && !map.queryRenderedFeatures(e.point, { layers: ["clusters", ...tappable] }).length) { state.venue = null; render(); }
    });
    map.on("movestart", () => { state.venue = null; });
    map.on("moveend", render);
    render();
  });
}

// For the smoke test and debugging: window.jcmaps.snapshot / .map / .state
window.jcmaps = { state, get snapshot() { return snapshot; }, get map() { return map; }, get current() { return current; } };

async function main() {
  readHash();
  syncControls();
  wire();
  try {
    const r = await fetch(DATA, { cache: "no-cache" });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    snapshot = await r.json();
  } catch (e) {
    $("#count").textContent = "Could not load events";
    $("#list").innerHTML = `<div class="empty">The event data did not load (${esc(e.message)}). Try again later.</div>`;
    return;
  }
  const age = (Date.now() - Date.parse(snapshot.generated_at)) / 36e5;
  if (age > 24) { $("#banner").textContent = `This data is ${Math.round(age / 24)} day${age >= 48 ? "s" : ""} old; the update did not run. Check the source links before you go.`; $("#banner").classList.add("on"); }
  if (typeof maplibregl === "undefined") { $("#list").innerHTML = ""; render(); return; }
  initMap();
}
main();
