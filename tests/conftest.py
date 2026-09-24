from datetime import datetime, timezone

import pytest

from pipeline.model import Raw


@pytest.fixture
def make_raw():
    def _make(**kw) -> Raw:
        base = dict(source_id="t", source_uid="1", title="Storytime", url="https://x/1",
                    start_utc=datetime(2026, 9, 26, 14, 30, tzinfo=timezone.utc), date="2026-09-26")
        base.update(kw)
        return Raw(**base)
    return _make
