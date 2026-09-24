import json

import httpx

from pipeline import cli, publish


def test_pull_writes_only_valid_files(tmp_path, monkeypatch):
    monkeypatch.setattr(publish, "SITE_DATA", tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("events.json"):
            return httpx.Response(200, text=json.dumps({"events": []}))
        if request.url.path.endswith("enrich.json"):
            return httpx.Response(200, text="not json")
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    got = cli.pull("https://example.org/jcmaps/", client)
    assert got == {"events.json": "14 bytes", "enrich.json": "JSONDecodeError", "geocode.json": "HTTP 404"}
    assert (tmp_path / "events.json").exists() and not (tmp_path / "enrich.json").exists()


def test_empty_environment_variables_mean_default(monkeypatch):
    from pipeline.util import env
    monkeypatch.setenv("JCMAP_COST_CAP_USD", "")
    assert float(env("JCMAP_COST_CAP_USD", "5")) == 5.0
    monkeypatch.setenv("JCMAP_COST_CAP_USD", "2.5")
    assert float(env("JCMAP_COST_CAP_USD", "5")) == 2.5
    monkeypatch.delenv("JCMAP_MODEL", raising=False)
    assert env("JCMAP_MODEL", "gpt-6-luna") == "gpt-6-luna"
