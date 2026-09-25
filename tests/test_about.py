"""The About page lists the sources the map shows, and the map links to it."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
ABOUT = (ROOT / "site" / "about.html").read_text()


def test_about_lists_every_published_source():
    published = {s["id"] for s in json.loads((ROOT / "city.json").read_text())["sources"] if s.get("publish")}
    assert set(re.findall(r'data-source="([\w-]+)"', ABOUT)) == published, "site/about.html lists city.json's published sources"


def test_the_map_links_to_about():
    assert (ROOT / "site" / "app.js").read_text().count('href="about.html"') == 2, "the map's credits and the list's footer"
