"""The model call's glue (cost, logging, refusal and error handling), exercised with a stub client."""
import json
from types import SimpleNamespace as NS

import openai
import pytest

from pipeline import llm
from pipeline.llm import EnrichOut

GOOD = EnrichOut(kid_friendly="yes", kid_friendly_quote="for ages 3-5", age_text="ages 3-5", age_min=3, age_max=5,
                 price="free", price_quote="free", price_text=None, registration="unknown", registration_quote=None,
                 organizer_type="city", organizer_type_quote="public library", status="scheduled", status_quote=None,
                 topics=["books"], summary="Stories for little ones.", venue_name=None, venue_address=None, venue_quote=None)


def usage(inp=900, out=300, cached=0):
    return NS(input_tokens=inp, output_tokens=out, input_tokens_details=NS(cached_tokens=cached))


class Stub:
    def __init__(self, response=None, error=None):
        self.calls, self.response, self.error = [], response, error
        self.responses = NS(parse=self._parse)

    def _parse(self, **kw):
        self.calls.append(kw)
        if self.error:
            raise self.error
        return self.response


@pytest.fixture(autouse=True)
def log_to_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "LOG", tmp_path / "llm.jsonl")


def test_success_logs_and_prices(tmp_path):
    stub = Stub(NS(status="completed", output_parsed=GOOD, usage=usage(cached=400), output=[]))
    call = llm.classify(stub, "title: Storytime", model="gpt-6-luna")
    assert call.error is None and call.out["kid_friendly"] == "yes" and call.out["topics"] == ["books"]
    assert call.cost_usd == round((500 * 0.10 + 400 * 0.01 + 300 * 0.50) / 1e6, 6)
    kw = stub.calls[0]
    assert kw["model"] == "gpt-6-luna" and kw["text_format"] is EnrichOut and kw["store"] is False
    assert kw["reasoning"] == {"effort": llm.EFFORT} and kw["instructions"] == llm.SYSTEM and kw["input"] == "title: Storytime"
    logged = json.loads((tmp_path / "llm.jsonl").read_text().splitlines()[-1])
    assert logged["input_hash"] == call.input_hash and logged["input_tokens"] == 900 and "out" in logged


def test_refusal_and_incomplete_become_errors():
    refusal = NS(status="completed", output_parsed=None, usage=usage(),
                 output=[NS(type="message", content=[NS(type="refusal", refusal="no")])])
    assert llm.classify(Stub(refusal), "x").error.startswith("status=completed refusal=no")
    incomplete = NS(status="incomplete", output_parsed=None, usage=usage(), output=[])
    assert llm.classify(Stub(incomplete), "x").error == "status=incomplete"


def test_api_errors_are_caught_and_logged(tmp_path):
    call = llm.classify(Stub(error=openai.APIConnectionError(request=None)), "x")
    assert call.error.startswith("APIConnectionError") and call.out is None
    assert len((tmp_path / "llm.jsonl").read_text().splitlines()) == 1


def test_unknown_model_is_priced_like_sol():
    assert llm.cost_of("gpt-7-mystery", usage(1_000_000, 0)) == 2.0


def test_no_key_means_no_client(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(llm, "ROOT", tmp_path)
    assert llm.make_client() is None
    (tmp_path / ".env").write_text("# local\nOPENAI_API_KEY='sk-test-123'\n")
    assert llm.api_key() == "sk-test-123"
