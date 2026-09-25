"""The rules of docs/design.md, checked: colors are tokens, text meets WCAG AA, the site is light only, the
copies that cannot read CSS (theme-color, manifest, icon) match their tokens, and every event type has an icon."""
import json
import re
from pathlib import Path

SITE = Path(__file__).parent.parent / "site"
TOKEN_CSS = (SITE / "tokens.css").read_text()
ROOT = re.search(r":root\s*\{(.*?)\}", TOKEN_CSS, re.S)
PAGES = {name: (SITE / name).read_text() for name in ("index.html", "about.html")}
STYLES = {name: re.search(r"<style>(.*?)</style>", html, re.S).group(1) for name, html in PAGES.items()}
COLOR = re.compile(r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})\b|\b(?:rgba?|hsla?|oklch|color-mix)\(")
TOKENS = {name: value.strip() for name, value in re.findall(r"--([\w-]+):([^;]+);", ROOT.group(1))}

# Foreground, background, minimum ratio: 4.5 for text, 3 for control borders (WCAG 2.2 AA).
PAIRS = [("ink", "surface", 4.5), ("ink-2", "surface", 4.5), ("ink-3", "surface", 4.5), ("ink-3", "surface-2", 4.5),
         ("surface", "ink", 4.5), ("ink-2", "accent-tint", 4.5), ("ink-3", "accent-tint", 4.5),
         ("on-accent", "accent", 4.5), ("free-text", "free-bg", 4.5), ("kids-text", "kids-bg", 4.5),
         ("ink-3", "map-land", 4.5), ("ink", "surface-2", 4.5), ("ink-2", "surface-2", 4.5), ("line-strong", "surface", 3)]


def luminance(color):
    channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    r, g, b = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_text_contrast():
    low = [f"--{fg} on --{bg} is {contrast(TOKENS[fg], TOKENS[bg]):.2f}, needs {need}"
           for fg, bg, need in PAIRS if contrast(TOKENS[fg], TOKENS[bg]) < need]
    assert not low, "\n".join(low)


def test_pins_stand_out_on_the_map():
    # A pin's outline is its fill or its ring, whichever differs more from what is under it; it needs 3:1.
    # Venues are addresses, so pins sit on land or in parks, never on water.
    low = [f"pins on --{under} reach {best:.2f}, need 3" for under in ("map-land", "map-park")
           if (best := max(contrast(TOKENS["accent"], TOKENS[under]), contrast(TOKENS["accent-edge"], TOKENS[under]))) < 3]
    assert not low, "\n".join(low)


def test_colors_are_tokens():
    assert not COLOR.findall(TOKEN_CSS.replace(ROOT.group(0), "")), "a color outside :root in tokens.css"
    for name, css in STYLES.items():
        assert '<link rel="stylesheet" href="tokens.css">' in PAGES[name], f"{name} does not load tokens.css"
        assert not COLOR.findall(css), f"a color in {name}; use a token from tokens.css"
        assert set(re.findall(r"var\(--([\w-]+)", css)) <= set(TOKENS), f"{name}: var() names a token that does not exist"
    for js in ("app.js", "icons.js"):
        assert not COLOR.findall((SITE / js).read_text()), f"a color in {js}; read a token instead"


def test_light_only():
    # Dark maps were hard to read; bringing a dark theme back is a decision for docs/design.md first.
    assert "prefers-color-scheme" not in TOKEN_CSS + "".join(PAGES.values()) + (SITE / "app.js").read_text()
    assert "color-scheme: light;" in ROOT.group(1)


def test_the_map_credits_its_data():
    # OpenStreetMap's license needs a credit linked to its copyright page, shown when the map opens; OpenMapTiles' needs
    # its own, in the map's corner. The credits line in app.js does both, so MapLibre's own control stays off.
    js = (SITE / "app.js").read_text()
    assert "attributionControl: false" in js and "© OpenMapTiles" in js
    assert '<a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">© OpenStreetMap</a>' in js


def test_copies_match_tokens():
    for name, html in PAGES.items():
        assert re.findall(r'"theme-color" content="([^"]+)"', html) == [TOKENS["map-land"]], name
    manifest = json.loads((SITE / "manifest.webmanifest").read_text())
    assert manifest["theme_color"] == manifest["background_color"] == TOKENS["map-land"]
    icon = re.findall(r'(?:fill|stroke)="([^"]+)"', (SITE / "icon.svg").read_text())
    assert TOKENS["accent"] in icon and set(icon) <= set(TOKENS.values()), "the icon uses the palette"


def test_every_type_has_an_icon_and_a_name():
    # One list of types in three places: the pipeline decides them, the site names and draws them.
    from typing import get_args

    from pipeline.enrich import TITLE_WORDS
    from pipeline.model import EventType
    js = (SITE / "icons.js").read_text()
    block = lambda name: re.search(rf"export const {name} = \{{(.*?)\}};", js, re.S).group(1)
    types, places = re.findall(r'(\w+): "', block("TYPES")), re.findall(r'(\w+): "', block("PLACES"))
    icons = dict(re.findall(r'(\w+): "([^"]+)"', block("ICONS")))
    assert types == [t for t, _ in TITLE_WORDS] == [t for t in get_args(EventType) if t != "unknown"]
    assert set(icons) == set(types) | set(places) | {"several"}
    assert all(re.fullmatch(r"M[\d.,\s\-A-Za-z]+", d) for d in icons.values()), "each icon is one SVG path"
