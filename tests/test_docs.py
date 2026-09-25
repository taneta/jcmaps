"""The docs keep up with the code: docs/how-it-works.md names every stage and page file, and every path the docs
name exists. Whether a diagram still draws the flow right is the pull request's check (AGENTS.md)."""
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
DOCS = [ROOT / "docs" / n for n in ("how-it-works.md", "routine.md", "sources.md")]
CODE = ["pipeline/**/*.py", "site/*.js", "site/*.html", ".github/workflows/*.yml"]
HELPERS = {"__init__.py", "model.py", "util.py", "geo.py", "search.test.js"}  # shared by stages, no flow of their own
PATH = re.compile(r"`((?:\.github|pipeline|site|docs|fixtures|data|tests)/[^`<>\s]*)`")


def test_how_it_works_names_every_code_file():
    text = DOCS[0].read_text()
    names = sorted({f.name for p in CODE for f in ROOT.glob(p)} - HELPERS)
    missing = [n for n in names if not re.search(rf"(?<![\w.-]){re.escape(n)}\b", text)]
    assert not missing, f"docs/how-it-works.md does not mention {missing}: add them to 'Where the code is'"


def test_paths_named_in_the_docs_exist():
    gone = [f"{doc.name}: {p}" for doc in DOCS for p in PATH.findall(doc.read_text())
            if not p.startswith("site/data/") and not (ROOT / p).exists()]
    assert not gone, f"the docs name paths that do not exist: {gone}"
