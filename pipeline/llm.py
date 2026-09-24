"""The one model call: no tools, schema-bound output, one vendor (OpenAI). Every call is appended to logs/llm.jsonl."""
from __future__ import annotations

import json
import os
import time
from typing import Literal

from pydantic import BaseModel, ConfigDict

from pipeline.util import ROOT, now_utc, sha

MODEL = os.environ.get("JCMAP_MODEL", "gpt-6-luna")
EFFORT = os.environ.get("JCMAP_EFFORT", "low")  # none | low | medium | high | xhigh | max
LOG = ROOT / "logs" / "llm.jsonl"
# USD per million tokens: input, output, cached input. An unknown model is priced like Sol so the cost cap errs safe.
PRICES = {"gpt-6-luna": (0.10, 0.50, 0.01), "gpt-6-sol": (2.0, 10.0, 0.20)}
TOPICS = ["music", "art", "books", "science", "games", "food", "outdoors", "sports", "film", "theater", "dance",
          "crafts", "history", "community", "health", "tech", "holiday", "market", "learning", "nightlife"]
Topic = Literal["music", "art", "books", "science", "games", "food", "outdoors", "sports", "film", "theater", "dance",
                "crafts", "history", "community", "health", "tech", "holiday", "market", "learning", "nightlife"]

SYSTEM = """You classify one Jersey City event listing at a time for a neighborhood events map.
You only fill in fields; you never invent events, venues, or dates.

Evidence rule: every field marked with a *_quote must be backed by a short verbatim quote copied exactly
from the listing (title, categories, cost, venue, or description). If the listing gives no direct evidence,
answer "unknown" (or null) and leave the quote null. Never paraphrase inside a quote.

kid_friendly: "yes" when the listing is for children, families, teens, or all ages, or is clearly suitable for
a child to attend with a parent. "no" only with explicit evidence such as 21+, 18+, adults only, singles,
mixer, happy hour, bar crawl, tasting, burlesque, mature content. Otherwise "unknown".
age_text: the listing's own words about ages, e.g. "ages 3-5" or "for ages 10-18"; age_min/age_max are the
numbers it implies (an open range like "9+" gives age_min 9 and age_max null). Null when not stated.
price: "free" only when the listing says free, no cost, or $0; "paid" when it names a price, fee, or tickets
for sale; otherwise "unknown". price_text is the listing's own words, e.g. "$20 suggested donation".
registration: "yes" when the listing asks people to register, RSVP, sign up, or buy tickets; "no" when it says
drop-in, walk-ins welcome, or no registration; otherwise "unknown".
organizer_type: "city" for the city government, public library, county, public schools, or another public
body; "business" for a company, bar, restaurant, shop, or commercial venue; "community" for a nonprofit,
church, club, arts organization, school PTA, or volunteer group; otherwise "unknown".
status: "cancelled" only when the listing says it is cancelled or postponed; otherwise "scheduled".
topics: up to three tags from the allowed list that best describe the event.
summary: at most 200 characters, in your own words, saying what happens and who it is for. Do not copy sentences.
venue_name, venue_address: only when the listing itself states where the event takes place, as a place name
and a street address; venue_quote is the exact text you took them from. Otherwise null.
"""


class EnrichOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kid_friendly: Literal["yes", "no", "unknown"]
    kid_friendly_quote: str | None
    age_text: str | None
    age_min: int | None
    age_max: int | None
    price: Literal["free", "paid", "unknown"]
    price_quote: str | None
    price_text: str | None
    registration: Literal["yes", "no", "unknown"]
    registration_quote: str | None
    organizer_type: Literal["city", "business", "community", "unknown"]
    organizer_type_quote: str | None
    status: Literal["scheduled", "cancelled", "unknown"]
    status_quote: str | None
    topics: list[Topic]
    summary: str
    venue_name: str | None
    venue_address: str | None
    venue_quote: str | None


class Call(BaseModel):
    input_hash: str
    model: str
    out: dict | None = None
    error: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0


def api_key() -> str | None:
    """OPENAI_API_KEY from the environment, or from a local .env file (ignored by git) for development."""
    if os.environ.get("OPENAI_API_KEY"):
        return os.environ["OPENAI_API_KEY"]
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            k, _, v = line.partition("=")
            if k.strip() == "OPENAI_API_KEY" and v.strip():
                return v.strip().strip("'\"")
    return None


def make_client():
    """None when there is no key: enrichment then falls back to the adapter rules and the cache."""
    key = api_key()
    if not key:
        return None
    import openai

    return openai.OpenAI(api_key=key)


def cost_of(model: str, usage) -> float:
    inp, out, cached_price = PRICES.get(model, PRICES["gpt-6-sol"])
    details = getattr(usage, "input_tokens_details", None)
    cached = getattr(details, "cached_tokens", 0) or 0
    return ((usage.input_tokens - cached) * inp + cached * cached_price + usage.output_tokens * out) / 1_000_000


def classify(client, text: str, model: str = MODEL) -> Call:
    import openai

    call = Call(input_hash=sha(text), model=model)
    t0 = time.monotonic()
    try:
        r = client.responses.parse(model=model, instructions=SYSTEM, input=text, text_format=EnrichOut,
                                   reasoning={"effort": EFFORT}, max_output_tokens=4096, store=False)
        call.input_tokens, call.output_tokens = r.usage.input_tokens, r.usage.output_tokens
        call.cost_usd = round(cost_of(model, r.usage), 6)
        refusal = next((c.refusal for o in r.output if o.type == "message" for c in o.content if c.type == "refusal"), None)
        if refusal or r.status != "completed" or r.output_parsed is None:
            call.error = f"status={r.status}" + (f" refusal={refusal[:120]}" if refusal else "")
        else:
            call.out = r.output_parsed.model_dump()
    except openai.OpenAIError as e:
        call.error = f"{type(e).__name__}: {str(e)[:200]}"
    call.latency_ms = int((time.monotonic() - t0) * 1000)
    LOG.parent.mkdir(exist_ok=True)
    with LOG.open("a") as f:
        f.write(json.dumps({"at": now_utc().isoformat(timespec="seconds"), **call.model_dump()}) + "\n")
    return call
