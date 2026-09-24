"""Records passed between stages. Raw is what an adapter reads; Event, Occurrence and Venue are published."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

KidFriendly = Literal["yes", "no", "unknown"]
Price = Literal["free", "paid", "unknown"]
OrganizerType = Literal["city", "business", "community", "unknown"]
Status = Literal["scheduled", "cancelled", "unknown"]
YesNo = Literal["yes", "no", "unknown"]
# One per event, decided by code in pipeline/enrich.py; each has an icon and a name in site/icons.js.
EventType = Literal["festivals", "markets", "stories", "games", "shows", "music", "health", "crafts", "classes",
                    "meetups", "unknown"]


class Evidence(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)
    quote: str
    from_: str = Field(alias="from")  # input field the quote came from, or "rule"


class Raw(BaseModel):
    """One feed entry as code parsed it. Enrichment input; the description is never published."""
    source_id: str
    source_uid: str
    title: str
    url: str
    description: str = ""
    categories: list[str] = []
    cost_text: str | None = None
    venue_name: str | None = None
    venue_address: str | None = None
    organizer_name: str | None = None
    start_utc: datetime
    end_utc: datetime | None = None
    all_day: bool = False
    date: str  # local calendar date, YYYY-MM-DD
    offsite: bool = False  # venue must come from the description
    venue_id: str | None = None  # set by the geocode stage
    alt_urls: list[str] = []  # URLs of records merged into this one as duplicates
    # fields an adapter rule can already decide, each with evidence
    kid_friendly: KidFriendly = "unknown"
    price: Price = "unknown"
    organizer_type: OrganizerType = "unknown"
    topics: list[str] = []
    evidence: dict[str, Evidence] = {}

    @property
    def id(self) -> str:
        return f"{self.source_id}:{self.source_uid}"

    def enrich_text(self) -> str:
        """The exact text the model sees; evidence quotes must be substrings of its normalized form."""
        parts = [f"title: {self.title}"]
        if self.categories:
            parts.append("categories: " + ", ".join(self.categories))
        if self.cost_text:
            parts.append(f"cost: {self.cost_text}")
        if self.venue_name or self.venue_address:
            parts.append(f"venue: {self.venue_name or ''} {self.venue_address or ''}".strip())
        parts.append(f"description: {self.description[:3000]}")
        return "\n".join(parts)


class Venue(BaseModel):
    id: str
    name: str
    aliases: list[str] = []
    address: str | None = None
    lat: float | None = None
    lon: float | None = None
    kind: str | None = None
    osm_id: str | None = None


class Event(BaseModel):
    id: str
    source_id: str
    source_uid: str
    title: str
    url: str
    organizer_name: str | None = None
    organizer_type: OrganizerType = "unknown"
    topics: list[str] = []
    type: EventType = "unknown"
    kid_friendly: KidFriendly = "unknown"
    age_min: int | None = None
    age_max: int | None = None
    age_text: str | None = None
    price: Price = "unknown"
    price_text: str | None = None
    registration: YesNo = "unknown"
    summary: str | None = None
    ongoing: bool = False
    status: Status = "scheduled"
    evidence: dict[str, Evidence] = {}
    alt_urls: list[str] = []
    first_seen: str
    last_seen: str
    updated_at: str


class Occurrence(BaseModel):
    event_id: str
    venue_id: str | None = None
    start_utc: datetime
    end_utc: datetime | None = None
    all_day: bool = False
    date: str
    tz: str = "America/New_York"


class Snapshot(BaseModel):
    generated_at: str
    city: dict
    sources: dict[str, dict]
    venues: list[Venue]
    events: list[Event]
    occurrences: list[Occurrence]
