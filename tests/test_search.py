import shutil
import subprocess
from pathlib import Path

import pytest

SITE = Path(__file__).parent.parent / "site"


@pytest.mark.skipif(shutil.which("node") is None, reason="node is needed for the search-rule tests")
def test_search_rules_in_node():
    run = subprocess.run(["node", "--test", "search.test.js"], cwd=SITE, capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
