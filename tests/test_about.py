"""The About page lists the sources the map shows, the map links to it, and every page counts visits."""
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


def test_every_page_counts_visits():
    uncounted = [p.name for p in (ROOT / "site").glob("*.html") if 'src="visits.js"' not in p.read_text()]
    assert not uncounted, f"{uncounted} do not load site/visits.js, so their visits go uncounted"


def test_a_report_from_a_card_carries_its_label_through_the_template():
    """GitHub applies the labels parameter only for people allowed to label issues; a template's labels apply to all."""
    template = (ROOT / ".github" / "ISSUE_TEMPLATE" / "report.md").read_text()
    assert "labels: report" in template
    app = (ROOT / "site" / "app.js").read_text()
    assert "issues/new?template=report.md&" in app and "labels=" not in app
