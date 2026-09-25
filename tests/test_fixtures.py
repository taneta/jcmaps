"""Fixtures hold what the tests need and nobody's contact details (docs/sources.md, rule 9). A feed is scrubbed as
it is read, so a frozen copy of the cache is clean by construction; this keeps it so."""
from pathlib import Path

from pipeline.util import scrub

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_scrub_replaces_contact_details_and_nothing_else():
    text = ('ORGANIZER;CN="A Person":MAILTO:aperson@jclibrary.org\r\nDTSTART:20260926T140000Z\r\n'
            "DESCRIPTION:Call (201) 547-4526\\, 201-547-4541 or 201.547.6996\\, or (201)   706-1870\\, "
            "or email a.person+x@jclibrary.org. UID 17175267-1 on 2026-09-24 at 10:30.\r\n")
    assert scrub(text) == ("DTSTART:20260926T140000Z\r\n"
                           "DESCRIPTION:Call 000-000-0000\\, 000-000-0000 or 000-000-0000\\, or 000-000-0000\\, "
                           "or email name@example.org. UID 17175267-1 on 2026-09-24 at 10:30.\r\n")


def test_every_fixture_is_scrubbed():
    dirty = [str(p.relative_to(FIXTURES)) for p in FIXTURES.rglob("*")
             if p.is_file() and scrub(p.read_text()) != p.read_text()]
    assert not dirty, f"contact details in {dirty}: refreeze through pipeline.util.scrub"
