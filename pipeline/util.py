"""Small shared helpers: paths, time zone, text normalization, JSON files."""
from __future__ import annotations

import hashlib
import html
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
TZ = ZoneInfo("America/New_York")
UA = "JCMaps/0.1 (non-commercial Jersey City events map)"
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE = re.compile(r"(?<!\d)\(?\d{3}\)?[-.\s]+\d{3}[-.\s]+\d{4}(?!\d)")


def env(name: str, default: str) -> str:
    """An environment variable, or the default when it is unset or empty (unset Actions variables arrive as '')."""
    import os

    return os.environ.get(name) or default


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def normalize(text: str) -> str:
    """Lowercase, plain quotes and dashes, single spaces. Used for evidence matching."""
    text = unicodedata.normalize("NFKC", text)
    for a, b in (("’", "'"), ("‘", "'"), ("“", '"'), ("”", '"'), ("–", "-"), ("—", "-")):
        text = text.replace(a, b)
    return re.sub(r"\s+", " ", text).strip().lower()


def scrub(text: str) -> str:
    """A feed without its contact details, applied as the feed is read so that neither the cache, the fixtures nor
    the model hold them (docs/sources.md, rule 9): email addresses and phone numbers become placeholders, and iCal
    ORGANIZER lines (staff names and addresses) go. The event's link carries the contact."""
    text = re.sub(r"^ORGANIZER.*\n", "", text, flags=re.M)
    return PHONE.sub("000-000-0000", EMAIL.sub("name@example.org", text))


def strip_html(text: str) -> str:
    text = re.sub(r"</(p|div|li|h\d|tr)>|<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n\s*\n\s*\n+", "\n\n", text).strip()


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text())


def write_json(path: Path, obj, compact: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    kw = {"separators": (",", ":")} if compact else {"indent": 1}
    path.write_text(json.dumps(obj, ensure_ascii=False, default=str, **kw) + "\n")
