"""Share links: one small page per event at site/e/<slug>/, so a link pasted in a chat previews the event. Chat apps
read a page's Open Graph tags without running its JavaScript, so each event gets a static page that carries the tags
(title; a description that opens with the day and start time; a map image with the pin) and sends a visitor on to
the map with the event open (site/app.js reads #e=<slug>). Map images come from headless Chrome with the site's own
basemap, rendered once per point and cached; without Chrome a preview has the text and no map."""
from __future__ import annotations

import base64
import html
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from pipeline.gate import looks_secret
from pipeline.util import ROOT, TZ

W, H, PANEL = 1200, 630, 200  # the preview image; the text panel along its bottom
PIN = (W // 2, (H - PANEL) // 2)  # where the event's point lands: the map is centered above the panel
ZOOM = 15
STYLE = "https://tiles.openfreemap.org/styles/positron"  # the page's basemap (site/app.js)
CREDITS = "© OpenStreetMap contributors · © OpenMapTiles"


def words(title: str, limit: int = 60) -> str:
    """"Café Night: Jazz & Poetry!" -> "cafe-night-jazz-poetry", cut at a word boundary."""
    ascii_ = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]+", "-", ascii_).strip("-")
    return s if len(s) <= limit else s[:limit].rsplit("-", 1)[0]


def slugs(ids_dates_titles: list[tuple[str, str, str]], previous: dict[str, dict]) -> dict[str, str]:
    """A readable link name per event: its local date and title ("2026-10-07-city-council-meeting"). An event keeps
    the name it was first published with, so a shared link never changes; a clash on the same day gets -2, -3."""
    out: dict[str, str] = {}
    for eid, _, _ in ids_dates_titles:
        old = previous.get(eid, {}).get("slug")
        if old and old not in out.values():
            out[eid] = old
    taken = set(out.values())
    for eid, day, title in ids_dates_titles:
        if eid in out:
            continue
        base = f"{day}-{words(title)}".rstrip("-")
        slug, n = base, 2
        while slug in taken:
            slug, n = f"{base}-{n}", n + 1
        out[eid] = slug
        taken.add(slug)
    return out


def clock(t: datetime) -> str:
    """6 PM, 6:30 PM."""
    return f"{t.hour % 12 or 12}{f':{t.minute:02d}' if t.minute else ''} {'AM' if t.hour < 12 else 'PM'}"


def when_text(occ: dict, ongoing: bool = False) -> str:
    """"Tue, Oct 7 · 6 PM", in Jersey City time; "Sat, Oct 3 · All day"; a run of days as "Sat, Oct 3 to Sun, Oct 25"."""
    start = datetime.fromisoformat(occ["start_utc"]).astimezone(TZ)
    day = f"{start:%a}, {start:%b} {start.day}"
    if ongoing and occ.get("end_utc"):
        end = datetime.fromisoformat(occ["end_utc"]).astimezone(TZ) - (timedelta(days=1) if occ.get("all_day") else timedelta())
        return f"{day} to {end:%a}, {end:%b} {end.day}"
    return f"{day} · All day" if occ.get("all_day") else f"{day} · {clock(start)}"


def place_text(venue: dict | None) -> str | None:
    """"Council Chambers, 280 Grove St": the venue's name and the street part of its address."""
    if not venue:
        return None
    name = (venue.get("name") or "").strip()
    street = (venue.get("address") or "").split(",")[0].strip().rstrip(".")
    if name and street and street.lower() not in name.lower() and name.lower() not in street.lower():
        return f"{name}, {street}"
    return name or street or None


def description(when: str, place: str | None, summary: str | None) -> str:
    """The day and start time first, then the place, then the one-line summary."""
    text = f"{when} · {place}" if place else when
    if summary:
        text += ". " + summary.strip()
    return text[:300]


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · JC Maps</title>
<meta name="description" content="{description}">
<link rel="canonical" href="{url}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="JC Maps">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{description}">
<meta property="og:url" content="{url}">
{image}<meta name="twitter:card" content="{card}">
<script>location.replace("../../#e={slug}")</script>
</head>
<body><p><a href="../../#e={slug}">{title}</a>: {description}</p></body>
</html>
"""
IMAGE = """<meta property="og:image" content="{src}">
<meta property="og:image:width" content="{w}">
<meta property="og:image:height" content="{h}">
<meta property="og:image:alt" content="{alt}">
"""


def page(event: dict, desc: str, url: str, image: str | None, alt: str) -> str:
    e = lambda s: html.escape(s, quote=True)  # noqa: E731
    img = IMAGE.format(src=e(image), w=W, h=H, alt=e(alt)) if image else ""
    return PAGE.format(title=e(event["title"]), description=e(desc), url=e(url), image=img, slug=event["slug"],
                       card="summary_large_image" if image else "summary")


def tokens() -> dict[str, str]:
    """The palette, read from site/tokens.css: no color is named anywhere else (docs/design.md)."""
    return dict(re.findall(r"--([\w-]+):\s*(#[0-9A-Fa-f]{6})\b", (ROOT / "site" / "tokens.css").read_text()))


def _fit(draw: ImageDraw.ImageDraw, text: str, font, width: int, lines: int) -> list[str]:
    """Wrap text into at most `lines` lines no wider than `width`, the last one ending in … if cut."""
    out, line = [], ""
    for word in text.split():
        if draw.textlength(f"{line} {word}".strip(), font=font) <= width:
            line = f"{line} {word}".strip()
            continue
        if line:
            out.append(line)
        line = word
        if len(out) == lines:
            break
    if line and len(out) < lines:
        out.append(line)
    if len(out) == lines and " ".join(out) != " ".join(text.split()):
        last = out[-1]
        while last and draw.textlength(last + "…", font=font) > width:
            last = last[:-1].rstrip()
        out[-1] = last + "…"
    return out


def preview(when: str, title: str, place: str | None, base: Path | None, c: dict[str, str]) -> Image.Image:
    """1200x630: the map with the event's pin, or plain land without one, and a panel with the day and start time,
    the title and the place. A selected pin on the site grows and glows; this one does too."""
    img = Image.open(base).convert("RGB").resize((W, H)) if base else Image.new("RGB", (W, H), c["map-land"])
    draw = ImageDraw.Draw(img)
    font = lambda size: ImageFont.load_default(size=size)  # noqa: E731
    if base:
        glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        x, y = PIN
        ImageDraw.Draw(glow).ellipse([x - 44, y - 44, x + 44, y + 44], fill=c["accent"] + "cc")
        img.paste(glow.filter(ImageFilter.GaussianBlur(14)), (0, 0), glow.filter(ImageFilter.GaussianBlur(14)))
        draw = ImageDraw.Draw(img)
        draw.ellipse([x - 26, y - 26, x + 26, y + 26], fill=c["accent"], outline=c["accent-edge"], width=4)
        draw.ellipse([x - 8, y - 8, x + 8, y + 8], fill=c["on-accent"])
        small = font(16)
        tw = draw.textlength(CREDITS, font=small)
        draw.rectangle([W - tw - 20, H - PANEL - 28, W, H - PANEL], fill=c["surface"])
        draw.text((W - tw - 10, H - PANEL - 24), CREDITS, font=small, fill=c["ink-3"])
    draw.rectangle([0, H - PANEL, W, H], fill=c["surface"])
    draw.line([(0, H - PANEL), (W, H - PANEL)], fill=c["line"], width=2)
    x0, y, width = 48, H - PANEL + 22, W - 96
    brand = font(24)
    draw.text((W - x0 - draw.textlength("jcmaps.com", font=brand), y + 10), "jcmaps.com", font=brand, fill=c["ink-3"])
    draw.text((x0, y), when, font=font(42), fill=c["ink"], stroke_width=1, stroke_fill=c["ink"])
    y += 56
    title_font = font(34)
    lines = _fit(draw, title, title_font, width, 2 if place else 3)
    for line in lines:
        draw.text((x0, y), line, font=title_font, fill=c["ink"])
        y += 42
    if place and len(lines) < 3:
        where = _fit(draw, place, font(26), width, 1)
        draw.text((x0, y + 4), where[0] if where else "", font=font(26), fill=c["ink-2"])
    return img


RENDER = """<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="https://unpkg.com/maplibre-gl@5/dist/maplibre-gl.css">
<script src="https://unpkg.com/maplibre-gl@5/dist/maplibre-gl.js"></script>
<style>html, body { margin: 0; overflow: hidden } #m { width: __W__px; height: __H__px }</style></head>
<body><div id="m"></div><script>
const T = __TOKENS__;
const map = new maplibregl.Map({ container: "m", style: "__STYLE__", center: [-74.06, 40.72], zoom: __ZOOM__,
  attributionControl: false, interactive: false, fadeDuration: 0 });
// The page's tint (tintBasemap in site/app.js): land, water, parks, buildings and place names in the palette.
function tint() {
  const prop = { background: "background-color", fill: "fill-color", symbol: "text-color" };
  for (const l of map.getStyle().layers) {
    const src = l["source-layer"];
    if (l.id.includes("shield")) { map.setLayoutProperty(l.id, "visibility", "none"); continue; }
    const name = l.type === "background" ? "map-land" : l.type === "symbol" ? (src === "place" ? "ink-3" : null) : l.type !== "fill" ? null
      : src === "water" ? "map-water" : src === "building" ? "map-building" : /park|wood|grass/.test(l.id) ? "map-park"
      : ["landuse", "landcover", "transportation"].includes(src) ? "map-land" : null;
    if (name) map.setPaintProperty(l.id, prop[l.type], T[name]);
  }
}
window.ready = new Promise((r) => map.on("load", () => { tint(); r(true); }));
window.show = async (lat, lon) => {
  map.jumpTo({ center: [lon, lat], zoom: __ZOOM__, padding: { bottom: __PANEL__ } });
  await new Promise((r) => { map.once("idle", r); setTimeout(r, 20000); });
  return map.loaded();
};
</script></body></html>"""
READY = "new Promise((r) => (function wait() { window.ready ? window.ready.then(r) : setTimeout(wait, 50); })())"


def chrome() -> str | None:
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        if found := shutil.which(name):
            return found
    mac = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    return mac if Path(mac).exists() else None


def render_maps(points: dict[str, tuple[float, float]], map_dir: Path) -> int:
    """Draw the basemap around each point (key -> lat, lon) into map_dir/<key>.jpg with headless Chrome, driven over
    the DevTools protocol: one browser for all points, so the style and tiles load once. Returns how many were drawn;
    a point that did not finish loading is left for the next run."""
    exe = chrome()
    if not points or not exe:
        if points:
            print("share: no Chrome, so previews have no map", file=sys.stderr)
        return 0
    from websockets.sync.client import connect

    map_dir.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="jcmaps-render-"))
    page_file = tmp / "render.html"
    page_file.write_text(RENDER.replace("__TOKENS__", json.dumps(tokens())).replace("__STYLE__", STYLE)
                         .replace("__ZOOM__", str(ZOOM)).replace("__PANEL__", str(PANEL))
                         .replace("__W__", str(W)).replace("__H__", str(H)))
    proc = subprocess.Popen([exe, "--headless=new", "--remote-debugging-port=0", f"--user-data-dir={tmp / 'profile'}",
                             f"--window-size={W},{H}", "--hide-scrollbars", "--no-first-run", "--use-angle=swiftshader",
                             "--enable-unsafe-swiftshader", page_file.as_uri()],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    drawn = 0
    try:
        port_file = tmp / "profile" / "DevToolsActivePort"
        for _ in range(300):
            if port_file.exists() and port_file.read_text().strip():
                break
            time.sleep(0.1)
        port = port_file.read_text().split()[0]
        target = next(t for t in httpx.get(f"http://127.0.0.1:{port}/json/list", timeout=10).json() if t["type"] == "page")
        with connect(target["webSocketDebuggerUrl"], max_size=None, open_timeout=20) as ws:
            n = 0

            def cdp(method: str, **params) -> dict:
                nonlocal n
                n += 1
                ws.send(json.dumps({"id": n, "method": method, "params": params}))
                while True:
                    msg = json.loads(ws.recv(timeout=90))
                    if msg.get("id") == n:
                        if "error" in msg:
                            raise RuntimeError(msg["error"])
                        return msg.get("result", {})

            cdp("Emulation.setDeviceMetricsOverride", width=W, height=H, deviceScaleFactor=1, mobile=False)
            cdp("Runtime.evaluate", expression=READY, awaitPromise=True)
            for key, (lat, lon) in points.items():
                done = cdp("Runtime.evaluate", expression=f"show({lat}, {lon})", awaitPromise=True, returnByValue=True)
                if not done.get("result", {}).get("value"):
                    continue
                shot = cdp("Page.captureScreenshot", format="jpeg", quality=85,
                           clip={"x": 0, "y": 0, "width": W, "height": H, "scale": 1})
                (map_dir / f"{key}.jpg").write_bytes(base64.b64decode(shot["data"]))
                drawn += 1
    except Exception as e:  # previews without a map are still previews
        print(f"share: map drawing stopped after {drawn}: {type(e).__name__}: {e}", file=sys.stderr)
    finally:
        proc.kill()
        proc.wait()
        shutil.rmtree(tmp, ignore_errors=True)
    return drawn


def point_key(venue: dict) -> str:
    return f"{venue['lat']:.5f}_{venue['lon']:.5f}"


def publish(snapshot: dict, city: dict, site_dir: Path, map_dir: Path, mode: str) -> dict:
    """Write site/e/<slug>/index.html for every event in the live snapshot, and its preview.jpg unless mode is "off".
    mode "maps" draws the map around new points first (render_maps); "text" makes previews without a map. The folder
    is rebuilt each run, so a page lives exactly as long as its event is published."""
    out = site_dir / "e"
    shutil.rmtree(out, ignore_errors=True)
    stats = {"pages": 0, "maps_drawn": 0, "maps_cached": 0, "without_map": 0}
    events = [e for e in snapshot.get("events", []) if e.get("slug")]
    if not events:
        return stats
    venues = {v["id"]: v for v in snapshot.get("venues", [])}
    occurrences = {o["event_id"]: o for o in snapshot.get("occurrences", [])}
    pinned = {e["id"]: v for e in events if (v := venues.get(occurrences[e["id"]]["venue_id"] or "")) and v.get("lat") is not None}
    if mode == "maps":
        points = {point_key(v): (v["lat"], v["lon"]) for v in pinned.values()}
        missing = {k: p for k, p in points.items() if not (map_dir / f"{k}.jpg").exists()}
        stats["maps_drawn"] = render_maps(missing, map_dir)
        stats["maps_cached"] = len(points) - len(missing)
    root = city["site_url"].rstrip("/") + "/"
    colors = tokens() if mode != "off" else {}
    for e in events:
        occ, venue = occurrences[e["id"]], venues.get(occurrences[e["id"]]["venue_id"] or "")
        when, place = when_text(occ, e.get("ongoing", False)), place_text(venue)
        desc = description(when, place, e.get("summary"))
        url = f"{root}e/{e['slug']}/"
        image = None
        if mode != "off":
            base = map_dir / f"{point_key(pinned[e['id']])}.jpg" if mode == "maps" and e["id"] in pinned else None
            base = base if base and base.exists() else None
            stats["without_map"] += base is None
            image = f"{url}preview.jpg"
        alt = f"Map of {place or 'Jersey City'} with the event's pin, {when}"
        text = page(e, desc, url, image, alt)
        if looks_secret(text):  # made from the snapshot the gate scanned; checked again all the same
            continue
        folder = out / e["slug"]
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "index.html").write_text(text)
        if image:
            preview(when, e["title"], place, base, colors).save(folder / "preview.jpg", "JPEG", quality=82, optimize=True)
        stats["pages"] += 1
    return stats
