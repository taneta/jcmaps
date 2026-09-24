"""The rules of docs/design.md, checked: colors are tokens, text meets WCAG AA in both themes, and the copies
that cannot read CSS (theme-color, manifest, icon) match their tokens."""
import json
import re
from pathlib import Path

SITE = Path(__file__).parent.parent / "site"
HTML = (SITE / "index.html").read_text()
CSS = re.search(r"<style>(.*?)</style>", HTML, re.S).group(1)
LIGHT = re.search(r":root\s*\{(.*?)\}", CSS, re.S)
DARK = re.search(r"prefers-color-scheme: dark\)\s*\{\s*:root\s*\{(.*?)\}", CSS, re.S)
COLOR = re.compile(r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})\b|\b(?:rgba?|hsla?|oklch|color-mix)\(")


def tokens(block):
    return {name: value.strip() for name, value in re.findall(r"--([\w-]+):([^;]+);", block)}


THEMES = {"light": tokens(LIGHT.group(1)), "dark": {**tokens(LIGHT.group(1)), **tokens(DARK.group(1))}}

# Foreground, background, minimum ratio: 4.5 for text, 3 for control borders (WCAG 2.2 AA).
PAIRS = [("ink", "surface", 4.5), ("ink-2", "surface", 4.5), ("ink-3", "surface", 4.5), ("ink-3", "surface-2", 4.5),
         ("surface", "ink", 4.5), ("ink-2", "accent-tint", 4.5), ("ink-3", "accent-tint", 4.5),
         ("on-accent", "accent", 4.5), ("free-text", "free-bg", 4.5), ("kids-text", "kids-bg", 4.5),
         ("ink-3", "map-land", 4.5), ("line-strong", "surface", 3)]


def luminance(color):
    channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    r, g, b = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_contrast_in_both_themes():
    low = [f"{theme}: --{fg} on --{bg} is {contrast(t[fg], t[bg]):.2f}, needs {need}"
           for theme, t in THEMES.items() for fg, bg, need in PAIRS if contrast(t[fg], t[bg]) < need]
    assert not low, "\n".join(low)


def test_pins_stand_out_on_the_map():
    # A pin's outline is its fill or its ring, whichever differs more from what is under it; it needs 3:1.
    # Venues are addresses, so pins sit on land or in parks, never on water.
    low = [f"{theme}: pins on --{under} reach {best:.2f}, need 3"
           for theme, t in THEMES.items() for under in ("map-land", "map-park")
           if (best := max(contrast(t["accent"], t[under]), contrast(t["accent-edge"], t[under]))) < 3]
    assert not low, "\n".join(low)


def test_colors_are_tokens():
    rest = CSS.replace(LIGHT.group(0), "").replace(DARK.group(1), "")
    assert not COLOR.findall(rest), "a color outside :root in index.html"
    assert not COLOR.findall((SITE / "app.js").read_text()), "a color in app.js; read a token instead"
    assert set(re.findall(r"var\(--([\w-]+)", CSS)) <= set(THEMES["light"]), "var() names a token that does not exist"


def test_copies_match_tokens():
    light, dark = THEMES["light"], THEMES["dark"]
    meta = {scheme: color for color, scheme in re.findall(r'"theme-color" content="([^"]+)" media="\(prefers-color-scheme: (\w+)\)"', HTML)}
    assert meta == {"light": light["map-land"], "dark": dark["map-land"]}
    manifest = json.loads((SITE / "manifest.webmanifest").read_text())
    assert manifest["theme_color"] == manifest["background_color"] == light["map-land"]
    icon = re.findall(r'(?:fill|stroke)="([^"]+)"', (SITE / "icon.svg").read_text())
    assert light["accent"] in icon and set(icon) <= set(light.values()) | set(dark.values()), "the icon uses the palette"
