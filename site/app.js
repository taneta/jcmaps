import { search, fromLocal, localParts } from "./search.js";

const REPO = "taneta/jcmaps"; // "Report a problem" opens a prefilled issue here
const DATA = "data/events.json";
const $ = (s) => document.querySelector(s);

const state = { window: "weekend", view: "family", freeOnly: false, childAge: null, venue: null, custom: null };
let snapshot = null, map = null, current = null, selected = null, glyphFont = null;

// ---- URL state, so a link can carry a filter ("weekend, free, age 5") ----
function readHash() {
  const p = new URLSearchParams(location.hash.slice(1));
  if (p.get("w")) state.window = p.get("w");
  if (p.get("v") === "everyone") state.view = "everyone";
  state.freeOnly = p.get("free") === "1";
  state.childAge = p.get("age") ? +p.get("age") : null;
  if (p.get("from") && p.get("to")) state.custom = { from: p.get("from"), to: p.get("to") };
}
function writeHash() {
  const p = new URLSearchParams();
  p.set("w", state.window);
  if (state.view === "everyone") p.set("v", "everyone");
  if (state.freeOnly) p.set("free", "1");
  if (state.childAge != null) p.set("age", state.childAge);
  if (state.window === "custom" && state.custom) { p.set("from", state.custom.from); p.set("to", state.custom.to); }
  history.replaceState(null, "", "#" + p.toString());
}

// ---- formatting ----
const tz = () => snapshot?.city?.tz || "America/New_York";
const fmtDay = (d) => new Intl.DateTimeFormat("en-US", { timeZone: tz(), weekday: "short", month: "short", day: "numeric" }).format(d);
const fmtTime = (d) => new Intl.DateTimeFormat("en-US", { timeZone: tz(), hour: "numeric", minute: "2-digit" }).format(d).replace(":00", "");
function when(occ) {
  const s = new Date(occ.start_utc);
  if (occ.all_day) return `${fmtDay(s)} · all day`;
  const t = fmtTime(s) + (occ.end_utc ? "–" + fmtTime(new Date(occ.end_utc)) : "");
  return `${fmtDay(s)} · ${t}`;
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
function card(item) {
  const { event: ev, occ, venue, labels } = item;
  const tags = [];
  if (ev.price === "free") tags.push('<span class="tag free">Free</span>');
  else if (ev.price === "paid") tags.push(`<span class="tag">${esc(ev.price_text || "Paid")}</span>`);
  if (ev.kid_friendly === "yes") tags.push('<span class="tag kids">Kids</span>');
  if (ev.age_text) tags.push(`<span class="tag">${esc(ev.age_text)}</span>`);
  if (ev.registration === "yes") tags.push('<span class="tag">Registration</span>');
  for (const l of labels) tags.push(`<span class="tag">${esc(l)}</span>`);
  if (venue && venue.lat == null) tags.push('<span class="tag">no map pin</span>');
  const where = venue ? venue.name : "Location not stated";
  return `<div class="card${selected === ev.id ? " sel" : ""}" data-id="${esc(ev.id)}" data-venue="${esc(occ.venue_id || "")}">
    <div class="when">${esc(when(occ))}</div>
    <h3>${esc(ev.title)}</h3>
    <div class="where">${esc(where)}${ev.organizer_name && ev.source_id !== "library" ? " · " + esc(ev.organizer_name) : ""}</div>
    ${ev.summary ? `<div class="sum">${esc(ev.summary)}</div>` : ""}
    <div class="tags">${tags.join("")}</div>
    <div class="links"><a href="${esc(ev.url)}" target="_blank" rel="noopener">Source ↗</a><a href="${reportUrl(ev)}" target="_blank" rel="noopener">Report a problem</a></div>
  </div>`;
}

function inView(item) {
  if (!map || !item.venue || item.venue.lat == null) return true; // unpinned items are always listed
  return map.getBounds().contains([item.venue.lon, item.venue.lat]);
}

function render() {
  if (!snapshot) return;
  const filter = { window: state.window === "custom" && state.custom ? customWindow() : (state.window === "custom" ? "weekend" : state.window),
    view: state.view, freeOnly: state.freeOnly, childAge: state.childAge };
  current = search(snapshot, filter, new Date());
  const shown = current.results.filter((i) => inView(i) && (!state.venue || i.occ.venue_id === state.venue));
  const ongoing = current.ongoing.filter((i) => !state.venue || i.occ.venue_id === state.venue);
  const venueName = state.venue && snapshot.venues.find((v) => v.id === state.venue)?.name;
  $("#count").textContent = `${shown.length} event${shown.length === 1 ? "" : "s"}${venueName ? " at " + venueName : " in view"}`;
  $("#hint").textContent = state.venue ? "clear pin ×" : current.results.length !== shown.length ? `${current.results.length} total` : "";
  let html = shown.map(card).join("");
  if (!shown.length) html = `<div class="empty">Nothing here for this window. Try another time, zoom out, or switch to Everyone.</div>`;
  if (ongoing.length) html += `<div class="section">Ongoing (${ongoing.length})</div>` + ongoing.map(card).join("");
  const gen = new Date(snapshot.generated_at);
  html += `<div class="foot">Updated ${fmtDay(gen)} ${fmtTime(gen)} · ${snapshot.events.length} events from ${Object.keys(snapshot.sources).length} sources · Times in Jersey City time.</div>`;
  $("#list").innerHTML = html;
  updatePins();
  writeHash();
}

function updatePins() {
  if (!map || !map.getSource("venues")) return;
  const counts = new Map();
  for (const i of current.results.concat(current.ongoing)) if (i.venue && i.venue.lat != null) counts.set(i.venue.id, (counts.get(i.venue.id) || 0) + 1);
  const features = snapshot.venues.filter((v) => counts.has(v.id)).map((v) => ({
    type: "Feature", geometry: { type: "Point", coordinates: [v.lon, v.lat] },
    properties: { id: v.id, name: v.name, count: counts.get(v.id), sel: v.id === state.venue ? 1 : 0 } }));
  map.getSource("venues").setData({ type: "FeatureCollection", features });
}

// ---- controls ----
function syncControls() {
  for (const b of document.querySelectorAll("#windows .chip")) b.setAttribute("aria-pressed", String(b.dataset.w === state.window));
  $("#dates").classList.toggle("on", state.window === "custom");
  $("#view").textContent = state.view === "family" ? "Family" : "Everyone";
  $("#view").setAttribute("aria-pressed", String(state.view === "family"));
  $("#free").setAttribute("aria-pressed", String(state.freeOnly));
  $("#age").value = state.childAge ?? "";
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
  $("#view").addEventListener("click", () => { state.view = state.view === "family" ? "everyone" : "family"; syncControls(); render(); });
  $("#free").addEventListener("click", () => { state.freeOnly = !state.freeOnly; syncControls(); render(); });
  $("#age").addEventListener("change", (e) => { const v = e.target.value; state.childAge = v === "" ? null : Math.max(0, Math.min(17, +v)); render(); });
  const sheet = $("#sheet");
  $("#handle").addEventListener("click", () => {
    if (state.venue) { state.venue = null; render(); return; }
    sheet.classList.toggle("full", !sheet.classList.contains("full") && !sheet.classList.contains("peek"));
    sheet.classList.toggle("peek", false);
  });
  $("#list").addEventListener("click", (e) => {
    if (e.target.closest("a")) return;
    const c = e.target.closest(".card"); if (!c) return;
    selected = c.dataset.id;
    const v = snapshot.venues.find((x) => x.id === c.dataset.venue);
    if (v && v.lat != null && map) map.flyTo({ center: [v.lon, v.lat], zoom: Math.max(map.getZoom(), 14.5) });
    for (const el of document.querySelectorAll(".card")) el.classList.toggle("sel", el.dataset.id === selected);
  });
}

// ---- map ----
function initMap() {
  const c = snapshot.city;
  map = new maplibregl.Map({ container: "map", style: "https://tiles.openfreemap.org/styles/liberty", center: c.center, zoom: 12.4,
    maxBounds: [[c.bbox[0] - 0.12, c.bbox[1] - 0.08], [c.bbox[2] + 0.12, c.bbox[3] + 0.08]], attributionControl: { compact: true } });
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
  map.addControl(new maplibregl.GeolocateControl({ positionOptions: { enableHighAccuracy: true }, trackUserLocation: false }), "top-right");
  map.on("load", () => {
    const styled = map.getStyle().layers.find((l) => l.layout && l.layout["text-font"]);
    glyphFont = styled ? styled.layout["text-font"] : ["Noto Sans Regular"];
    map.addSource("venues", { type: "geojson", data: { type: "FeatureCollection", features: [] }, cluster: true, clusterRadius: 36, clusterMaxZoom: 14,
      clusterProperties: { count: ["+", ["get", "count"]] } });
    map.addLayer({ id: "clusters", type: "circle", source: "venues", filter: ["has", "point_count"],
      paint: { "circle-color": "#1e40af", "circle-radius": ["step", ["coalesce", ["get", "count"], 0], 16, 10, 20, 40, 25], "circle-stroke-width": 2, "circle-stroke-color": "#fff", "circle-opacity": 0.9 } });
    map.addLayer({ id: "cluster-count", type: "symbol", source: "venues", filter: ["has", "point_count"],
      layout: { "text-field": ["to-string", ["get", "count"]], "text-font": glyphFont, "text-size": 13, "text-allow-overlap": true }, paint: { "text-color": "#fff" } });
    map.addLayer({ id: "pins", type: "circle", source: "venues", filter: ["!", ["has", "point_count"]],
      paint: { "circle-color": ["case", ["==", ["coalesce", ["get", "sel"], 0], 1], "#dc2626", "#1d4ed8"], "circle-radius": ["step", ["coalesce", ["get", "count"], 0], 9, 3, 12, 8, 15], "circle-stroke-width": 2, "circle-stroke-color": "#fff" } });
    map.addLayer({ id: "pin-count", type: "symbol", source: "venues", filter: ["all", ["!", ["has", "point_count"]], [">", ["coalesce", ["get", "count"], 0], 1]],
      layout: { "text-field": ["to-string", ["get", "count"]], "text-font": glyphFont, "text-size": 11, "text-allow-overlap": true }, paint: { "text-color": "#fff" } });
    map.on("click", "clusters", (e) => {
      const f = map.queryRenderedFeatures(e.point, { layers: ["clusters"] })[0];
      map.getSource("venues").getClusterExpansionZoom(f.properties.cluster_id).then((z) => map.easeTo({ center: f.geometry.coordinates, zoom: z }));
    });
    map.on("click", "pins", (e) => {
      const f = e.features[0];
      state.venue = state.venue === f.properties.id ? null : f.properties.id;
      $("#sheet").classList.remove("peek");
      render();
    });
    for (const l of ["clusters", "pins"]) { map.on("mouseenter", l, () => (map.getCanvas().style.cursor = "pointer")); map.on("mouseleave", l, () => (map.getCanvas().style.cursor = "")); }
    map.on("moveend", () => { if (!state.venue) render(); });
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
