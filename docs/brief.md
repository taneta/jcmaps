# Jersey City events map: brief v0.4

Amended 2026-09-24 after day one: the project is named JCMaps; the model vendor is OpenAI (gpt-6-luna); generated data is not committed, the live site is the state between runs and reports and logs are workflow artifacts (see AGENTS.md and README).

Supersedes v0.3 on 2026-09-24. What changed: the app comes first and the AI-development harness is a by-product; the data is general with a family view by default; v1 is built in one day; there is no database, no agent machinery and one model vendor in v1; every source is verified with its URL; every automatic check has a safe response and a repair path (see Checks and loops).

## Product

A map-first web app for Jersey City that answers one question: what is happening in the city in a chosen time window. It runs in a phone browser and can be added to the home screen. The user picks a window, sees events as pins on a map and as a list, and each event shows what, where, when, whether it is free, who it suits, and a link to the source.

The data is general: city, business and community events, for adults and children alike. The view is family by default: events marked not kid-friendly are hidden until the user switches to Everyone. Reason: the open sources are mostly adult events, the data model already carries both, and a family default is what makes the app shareable among parents.

- **v1, one day:** feeds from the library and the city, refreshed twice a day, on a static map. No accounts, no database, no user input.
- **v1.x:** more sources, a weekly coverage check against the baseline, and an About page with a suggestion form: a
  Google Form that only the owner reads, so nothing a visitor sends reaches the pipeline.
- **v2:** organizers add events from a flyer photo or text; a checker screens them.
- **v3:** plain-language search and an MCP server over the same filter.

What v1 is not: events that exist only on Instagram or a flyer taped to a pole. Those arrive in v2.

**Baseline.** The JC Families weekly roundup, Macaroni KID Jersey City, the library calendar and Instagram. Once a week for the first month, compare the app's weekend list against the first two by hand. Every event they have and the app lacks becomes a candidate source.

**Distribution.** A standalone site is found by nobody. Be infrastructure instead: an embeddable version of the map for other sites, a plain link for parent groups and PTAs, and in v3 an MCP server so assistants can answer from it. Partnerships with the library, Cultural Affairs and JC Families come after the idea is final.

## Build rules (the core of AGENTS.md)

1. **Lowest rung that works.** Feeds are parsed by code. Model calls are single functions: no tools, schema-bound output, one vendor, one file. No agents in the pipeline. Only code writes files or publishes.
2. **Evidence or unknown.** Every model-filled field carries a quote from the input. No quote, no value: the field is `unknown`, and the UI shows unknown rather than guessing.
3. **One acceptance command per step.** Fixtures are frozen in the repo, tests run offline, and a step is done when its command passes.
4. **Every model call is logged** to a JSONL file: input hash, output, model, tokens, cost, latency.
5. **Secrets never reach a model.** In v1 the only secret is the model API key, stored as a GitHub Actions secret.
6. **Grow by adding.** One module and one fixture folder per source. New channels and endpoints sit beside the old ones. Migrations are fine when needed.

`AGENTS.md` holds these rules, the commands and the layout in under 60 lines, because it is loaded on every turn; `CLAUDE.md` imports it. This brief lives in `docs/brief.md` and is read only when a decision needs context.

## Sources

Verified 2026-09-24. Three adapters cover the five feeds: LibCal, The Events Calendar and any other iCal feed.

| Source | Access | What is there |
|---|---|---|
| Jersey City Free Public Library | LibCal iCal feed per calendar: `https://jclibrary.libcal.com/ical_subscribe.php?src=p&cid=<cid>` | 15 calendars. Main library 210 entries, Pavonia 150, Spotlight 31, reaching about three months ahead. Fields: SUMMARY, DTSTART, DTEND, LOCATION, DESCRIPTION, URL, CATEGORIES. Categories include Storytime Events, Children Events, All-Ages Events |
| Barrow Mansion | Same API as Cultural Affairs: `https://barrowmansion.org/wp-json/tribe/events/v1/events` | 64 upcoming, to September 2027, all at 83 Wayne St: weekly meditation, fundraisers and the Van Vorst Neighborhood Association's meetings, which are skipped because the association lists them a week later |
| Art House Productions | A Shopify collection as JSON: `https://www.arthouseproductions.org/collections/upcomingevents/products.json` | 15 items on 2026-09-26: shows, screenings and concerts at 345 Marin Blvd, two gallery exhibitions and the Lincoln Park flags as ongoing items, JC Fridays. The $0 price is a placeholder; a run such as RENT gives way to the city's dated showings |
| JC Office of Cultural Affairs | The Events Calendar API: `https://jerseycityculture.org/wp-json/tribe/events/v1/events` | 68 upcoming, mostly free community events, venue addresses, no coordinates |
| New Jersey Department of Health | A statewide CSV: `https://www.nj.gov/health/assets/documents/community-calendar.csv` | 103 rows on 2026-09-26, 6 at a Jersey City venue: free flu and COVID clinics at library branches and a farmers market. Four columns name people and are dropped on download |
| City of Jersey City | iCal feed: `https://www.jerseycitynj.gov/ICalendarHandler?calendarId=12409811` | 122 entries from June 2026 to October 2027, 19 in the next 30 days: council, caucus and board meetings, Senior Freeze help, court outreach. No links and no prices; the event page is `https://www.jerseycitynj.gov/workspaces/one.aspx?objectId=<UID>&contextId=12409811` |
| Hudson County Community College | Modern Campus JSON: `https://api.calendar.moderncampus.net/pubcalendar/310cd426-7d96-4d87-bab8-018335d68d75/events?start=&end=` (the iCal twin has no categories or links) | 96 entries in the month on 2026-09-26, most academic deadlines or admissions visits; the public categories at the Jersey City campuses come through, virtual and off-campus ones do not |
| Jersey City Connects | Same API: `https://jerseycityconnects.com/wp-json/tribe/events/v1/events` | An adult social club: mixers, game nights, some events outside the city |
| Saint Peter's University Athletics | One iCal feed for every sport: `https://saintpeterspeacocks.com/calendar.ashx/calendar.ics?sport_id=0` | 179 entries for the season. Home games ("vs", at the Yanitelli Center or Jaroschak Field) are kept; away games and games without a venue are not. robots.txt asks for a 30 s crawl delay; the run makes one request |
| Riverview Farmers Market | Same API: `https://riverviewfarmersmarket.org/wp-json/tribe/events/v1/events` | 14 upcoming, to December, in Riverview-Fisk Park (498 Palisade Ave): yoga, qigong, crafts, Day of the Dead, the Heights Holiday Market; mostly marked Free |
| Hudson County | Same API: `https://www.hcnj.us/wp-json/tribe/events/v1/events` | 31 upcoming on 2026-09-26: 9 with a Jersey City venue (planning board, a food pantry summit); the county commissioners' meetings and the virtual ones name no place and are left out (`require_venue`) |
| JC Families | Same API: `https://jcfamilies.com/wp-json/tribe/events/v1/events` | 10 upcoming. Baseline only until they have been asked; their curation is their product |

Library calendar ids: Main 17419, Morgan 17420, West Bergen 17421, Pavonia 17422, Miller 17423, Marion 17424, Lafayette 17425, Heights 17426, Cunningham 17427, Five Corners 17430, Bookmobile 17432, Communipaw 19967, Creative Arts Center 20079, Spotlight 20148, Learning Center 21694.

Source rules:
- **The library venue is the calendar**, not the LOCATION field, which holds room codes such as `PGML- Bonetti Room`. Exceptions: Bookmobile and Spotlight, where LOCATION says "Offsite" and the address is in the description; enrichment extracts it.
- **Library audience** comes from categories: Storytime, Children and All-Ages mean kid-friendly yes; Adults (19+) means no.
- **Library price** is free by adapter rule, with "library program" recorded as the evidence, unless the listing talks about money: a price, a fee, a cost, a fundraiser, or a ticket in a sentence about buying it (branches also hand out free entry tickets). Then the model decides, with a quote. The word "free" decides nothing on its own, because it is part of the library's name.
- **An empty `cost` field in The Events Calendar means unknown, not free.** Only the word free or a zero means free.
- **A free-text iCal LOCATION** is split at the house number into a venue name and an address, which gets a comma before the city so it keys like other sources' ("Council Chambers 280 Grove St. Jersey City NJ"). A named place without an address, such as City Hall, takes its address from `places` in city.json. Zoom or an empty location means no venue: the event is listed without a pin.
- **Farmers markets and street fairs on the city's calendar are free to enter**, by the owner's rule, like the library's. It applies only when nothing else decided the price and the listing does not talk about money; the title words ("Farmers Market") are the evidence, marked as a rule.
- **Boundary:** occurrences outside the city polygon are dropped and counted in the run report.
- **A venue's copy of another organizer's event is skipped when the organizer's own site disagrees**, so the organizer's listing wins: `skip` in city.json, counted in the run report. Barrow Mansion lists the Van Vorst meetings on second Tuesdays, the association on third.

Not now: Instagram, Facebook and the other social platforms (their terms forbid collection; v2 covers them through flyers), Macaroni KID (blocks scripted requests; baseline by hand).

Promising, later: Eventbrite's API, read by venue with a free token. It would bring the Landmarks Conservancy's walking tours, Sustainable JC, JCAST tickets and Liberty Science Center's special events, but the token is a second secret, and Eventbrite's terms allow storing only future events, each with a direct link.

Candidates, checked 2026-09-24 in a sweep of about 120 sources: the ones with a usable feed are tickets #41 and #43 to #50, and most of the rest need the organizer's permission first. The city's own calendar has an iCal feed after all, and Meetup groups have free ones. Mana Contemporary has a feed with about one event a month.

The rules for collecting, and what never goes on the map, are in `docs/sources.md`.

## Pipeline

Stages are plain functions with files between them. The scheduled job runs them in order; v2's submission endpoint calls the same functions. Stage outputs are keyed by a hash of the raw input, so unchanged inputs skip the model.

1. **Fetch.** Each adapter downloads its feed to `cache/`, which is not committed. Fixtures are.
2. **Parse.** Code turns the feed into Event and Occurrence records: source uid, title, times in UTC, venue name and address, description text, categories, cost text, URL. Date-only entries are all-day. If an RRULE appears, expand it for 30 days.
3. **Geocode.** Venue address to coordinates, cached in the repo. One venue per address: records with the same house number, street and city share it however each source spells them, and the other names become aliases. Nominatim at one request per second with a User-Agent, or Photon. Known venues (the library branches, seeded once from OpenStreetMap, and any venue a person corrects) are pinned from `data/venue_points.json` and never geocoded; a street answer to a query with a house number counts as no answer. An event that fails to geocode keeps its record and is shown in the list without a pin, and the run report lists such venues with their event counts.
4. **Enrich.** One model call per new or changed event. Input: title, description, categories, cost text, venue, source name. Output, schema-bound, each field with an evidence quote: `kid_friendly`, `age_min`, `age_max`, `age_text`, `price`, `price_text`, `organizer_type`, `topics`, `summary`, `status`, and for offsite library events the venue name and address. `kid_friendly: no` requires explicit evidence such as 21+, adults only, singles, mixer, happy hour. Each quote must be a substring of the normalized input, or the field becomes unknown. The model never creates, merges or deletes events, so invented events are impossible by construction. Code, not the model, also gives each event one type for its icon: the first type whose words are in the title, else in the feed's own categories, with the matched words as evidence; no match is `unknown`.
5. **Check.** Rules only in v1: required fields, start in the future or ongoing, inside the boundary, duplicates. Duplicates share a venue and a date, overlap in time and have similar titles, or one title starts with the other's first three words; the record with more evidence wins and keeps every URL. A title containing cancelled or postponed sets the status to cancelled. Failures go to the run report with a reason.
6. **Publish.** Write `site/data/events.json` (events, occurrences, venues, generated_at) and the run report; the workflow deploys `site/` to GitHub Pages. Nothing is committed: the next run pulls the snapshot and caches back from the live site. The snapshot passes the publish gate first, compared with the last good snapshot; if it fails, the last good snapshot stays and an issue opens. The job runs twice a day, about 2am and 7am local time (cron is in UTC), fetching each feed spaced as its host's robots.txt asks; a merge rebuilds from the feeds the last run saved, without fetching (#42). Cancellations show within hours because feeds are re-read on every scheduled run.

Run report per run: events and state per source, drops with reasons, geocode failures, model calls, cost, duration, the gate result. A source that cannot be fetched or returns zero events opens a GitHub issue.

## Data model

```
Source      id, name, kind (ics|tribe|page), url, state (active|degraded|down),
            carried_from, last_run, last_count, last_good_count
Venue       id, name, aliases[], address, lat, lon, kind, osm_id
Event       id, source_id, source_uid, title, url, organizer_name,
            organizer_type (city|business|community|unknown), topics[],
            type (festivals|markets|stories|games|shows|music|health|crafts|classes|meetups|unknown),
            kid_friendly (yes|no|unknown), age_min, age_max, age_text,
            price (free|paid|unknown), price_text, registration (yes|no|unknown),
            summary (own words, <=200 chars), ongoing (bool),
            status (scheduled|cancelled|unknown), evidence {field: {quote, from}},
            first_seen, last_seen, updated_at
Occurrence  event_id, venue_id|null, start_utc, end_utc|null, all_day, tz
Filter      window_start, window_end, bbox, view (family|everyone), free_only,
            topics[]      # shared by the UI, v3 search and the MCP tool
Submission  (v2) id, channel (photo|text), raw_ref, input_hash, submitter_id,
            status (pending|published|rejected|escalated), reason, created_at
```

Raw text fields such as `age_text` and `price_text` are kept and shown, because "ages 9+" reads better than a parsed range. An ongoing item, such as a three-month exhibition, is a flag on the event, not a kind of occurrence; ongoing items sit in their own layer outside time-window results.

## Search rules

- Time zone America/New_York; store UTC plus the zone.
- An occurrence matches a window if it starts before the window ends and ends after it starts. A missing end means two hours. All-day items match any window on their date.
- Windows: Today (from now until midnight, so what ended earlier today is gone and what is under way stays; the default), Tomorrow, Weekend, or Dates, a custom range up to 30 days ahead.
- **View.** Family, the default, hides `kid_friendly: no`. Everyone shows all. Unknown is always shown, with a label.
- **Free only** shows `price: free`, so stating a price never costs an event visibility and saying "free" earns it; hiding only known-paid events would reward listings that say nothing. While Free is on, the list says how many events it left out for not listing a price. Without Free, unknown prices carry a "price not listed" label.
- Ongoing items appear in a separate layer.

The rules are pure functions over the snapshot, tested with a fixed clock.

## Frontend

Static, no framework: one HTML file and one module. MapLibre GL JS with a vector basemap, clustered pins from a GeoJSON source, and a bottom-sheet list that follows the viewport: the count is the pinned events in view, events without a pin sit under their own heading, and a tapped pin lists its venue's events until the map moves. The map stays north-up and flat. Controls: time chips (Today, Tomorrow, Weekend, Dates), Family or Everyone, Free. Each pin shows one icon for what is on there and a badge with its count; when its events are of several types it shows the place's own icon (a library) or a calendar (see `docs/design.md`, Icons). An event card starts with its event's icon and type, and shows title, time, venue, price, ages, summary, the source link and a "Report on GitHub" link that opens a prefilled issue with the event id and a reason. The page shows when the snapshot was generated and a warning banner when it is older than a day. Phone width first, tap targets of 44 px, no horizontal scroll. A manifest for add-to-home-screen; a service worker that caches the snapshot is optional.

Basemap: OpenFreeMap's hosted `positron` style, tinted with the palette in `docs/design.md`; no key, no file. Day one used `liberty`. In v1.x, a PMTiles extract of the city from Protomaps' daily build (`pmtiles extract https://build.protomaps.com/<date>.pmtiles jc.pmtiles --bbox=-74.13,40.65,-74.01,40.78`), one static file on Pages, for independence.

Visits: GoatCounter, without cookies. Once a day each browser also reports "new" or "returning", from the date of its last visit, which only the browser keeps. Cloudflare Web Analytics keeps nothing in the browser, but it cannot count returning visitors and takes no custom events.

## Security

Untrusted text from any feed reaches the enrichment model. The defenses are structural: the call has no tools, its output must match the schema, it can only fill fields on events that code created, and code alone writes and publishes. No secret is ever in a model's context; the repair agent edits code and opens pull requests, while CI, not the agent, runs anything that needs the API key. v2 adds submissions and with them a checker on a different model that sees only extracted JSON and evidence, EXIF stripped on upload, a required poster identity, and enrichment fetches limited to the event's own domain.

## Evaluation, right-sized

- **Adapter contract tests** on frozen fixtures: the library feeds and one page of each API, downloaded once on day one. They assert counts, sample fields and time zone handling.
- **Search-rule tests** cover each window and filter against a fixed clock.
- **Enrichment hand-check:** `uv run jcmaps eval-enrich` prints 30 events with their model-filled fields and quotes. Target: no `no` and no `paid` without a quote; unknown is fine. Record the number of wrong fields in `docs/numbers.md`, and freeze the corrected 30 as the labeled set in `fixtures/labeled/enrich.json`.
- **Run report** on every run, as above.
- **Coverage** weekly by hand against the baseline for the first month.
- Later: a 50-item real set frozen before any change to the enrichment prompt; synthetic flyers and seeded bad submissions for v2's checker; the query round-trip test for v3.

## Checks and loops

A closed loop has three parts: a check that runs without a person, a response that is safe without a person, and a path to a fix that does not depend on a person noticing. Every check below produces a signal, every signal has an automatic response, and every response corrects the data, degrades safely, or opens an issue that the repair loop can pick up. Thresholds are provisional until a week of runs has calibrated them.

| Check | Signal | Automatic response | Closed by |
|---|---|---|---|
| Evidence is real | A quote is not a substring of the normalized input | The field becomes unknown | Code, per item |
| Publish gate | A past occurrence, a pin outside the boundary, no events at all, a schema failure, anything shaped like a key | The last good snapshot stays; an issue opens | Code, then repair |
| Source health | A source's fetch fails, or its feed lists over 30% fewer events than the source published last time (#30) | The source is degraded: its last good events are carried forward for 24 hours after its last successful fetch, and the same checks and gate judge them. Then a failed source is down, left out without failing the gate until it answers again, and a shrunken feed is published as it is, which settles the comparison. Either way an issue opens | Code, then repair |
| Cancellations | "Cancelled" or "postponed" in a title, or an occurrence gone from its feed | Marked cancelled and hidden. Each run rebuilds from the feeds, so a vanished occurrence drops on the next run; data carried forward for a degraded source drops 24 hours after its last successful fetch | Code |
| Model drift | The labeled set re-enriched weekly; agreement under 90% | New enrichments rejected, cached values kept, an issue opens | Code; a person picks the prompt or model |
| Change control | Any change to the prompt or model | Scored on the labeled set first; replaces cached values only if it scores at least as well | Code |
| Cost cap | Model spend over the cap during a run | Enrichment stops, the run publishes from cache, an issue opens | Code |
| Freshness | The snapshot is older than a day | A banner on the site; an issue opens | Code, then repair |
| Site smoke test | On a deploy, the page fails to load the snapshot or render pins in headless Chromium | The deploy is rejected | Code |
| User reports | "Report on GitHub" on each card, with a reason | An issue with the event id and reason; in v2 the post is also hidden pending a recheck | Repair triages; a person merges |
| Repair | Any issue with an `auto:` label | A scheduled agent run reads the issue and the run report, refreezes the fixture from the live source, fixes the adapter or prompt, and opens a pull request; CI runs the tests and the labeled set | The gates decide; a person merges the first five |

- **The labeled set** is the 30 hand-checked events from day one, corrected and frozen in `fixtures/labeled/enrich.json`. It serves the drift canary, change control and CI, and it grows with every user report that turns out to be right.
- **No second-model checker in v1.** Every v1 event exists because a feed said so, so existence needs no checking; the model only classifies. The substring rule catches a hallucinated quote deterministically and the weekly canary catches drift. The checker on a different model returns in v2, when input becomes untrusted.
- **The repair loop** is v0.3's self-repair scoped down from "agents write parsers for new sources" to "agents fix what the checks flag." The gates make it safe, not the agent: its pull request passes the same tests and the same labeled set as any other change. The agent edits and opens the pull request; CI, not the agent, runs anything that needs the API key, so no secret enters the agent's context, and the agent fetches only source domains.
- **The process loop.** The done-when column in the day-one table is the prediction; `docs/numbers.md` records the outcome.
- **Timing.** Day one includes the substring rule, the cancelled-title rule, the publish gate, the freshness banner and the report link. Source health for failed fetches came with the first real breakage, a few minutes of one feed's outage that froze every source (#21). The drift canary, change control, the cost cap and the smoke test come after a week of runs has produced numbers to set thresholds against. The repair agent is set up after the first real breakage, so it is designed against a real failure rather than a guessed one.

## Day one

Appetite: one day. Steps in order, each with a done-when; the budgets sum to about ten hours, which is why the cut list exists. If the day runs long, cut features from the cut list rather than skipping steps.

| # | Step | Budget | Done when |
|---|---|---|---|
| 0 | Repo, `uv`, `AGENTS.md`, `city.json` with the boundary polygon from OpenStreetMap, the time zone and the source list; Actions and Pages skeleton | 45 min | `uv run pytest` passes on an empty suite; Pages serves a placeholder |
| 1 | Library adapter: fetch the 15 feeds, parse, branch venue table, fixtures, contract test | 75 min | `uv run jcmaps build --source library` yields occurrences for the next 30 days; the test passes |
| 2 | The Events Calendar adapter for the two city feeds; geocoder with cache | 60 min | 95% of occurrences have coordinates |
| 3 | Enrichment call, schema, JSONL log, the evidence substring rule; run on everything; hand-check 30 and freeze them as the labeled set | 90 min | The eval table is reviewed; every quote is found in its input; no `no` or `paid` without a quote |
| 4 | Check and publish: rules, duplicates, the cancelled-title rule, the publish gate, snapshot, report | 60 min | `site/data/events.json` is written; the report lists drops; a snapshot that fails the gate is not published and the last good one stays |
| 5 | Frontend: map, pins, list, filters, card with a report link, a generated-at line and a stale banner | 180 min | On a phone, Weekend shows what the search-rule tests say it should; the report link opens a prefilled issue |
| 6 | Deploy and schedule: Pages, cron, secret | 45 min | A scheduled run commits a new snapshot |
| 7 | Spot-check 20 events against their sources; share the link | 30 min | Live |

Cut list, in order: the service worker; clustering; the age field; Jersey City Connects; enrichment (ship with library categories for kid-friendliness, price unknown outside the library, organizer type from the source).

Numbers to record at the end of the day: events per source, share geocoded, wrong fields out of 30, cost per run.

## After day one

- **v1.x:** probe the candidate sources one at a time with the same adapter pattern, feeds first; the PMTiles basemap; the weekly coverage check; pin styles per organizer type; after a week of runs, the drift canary, change control, the cost cap and the site smoke test; after the first real breakage, the repair agent.
- **v2:** organizer submissions. `POST /submissions` with a photo or text runs the same parse and enrich functions and returns a confirmation card (the actual date, noon versus midnight, the pin); `POST /submissions/{id}/confirm` sends it through the checker. Posters identify as a named organizer or person. Reports hide a post and the checker reviews it again. This is where a backend and a database first appear: Cloudflare Workers with D1 and R2, or Supabase. Aimed at organizers, who have the flyer and want the reach; parents mostly will not post.
- **v3:** an MCP server with `search_events(Filter)` and `get_event(id)`; the app's plain-language search is a thin client that maps text to a Filter, and any assistant can use the same server.

Not now: accounts before v2, voice input, RSVPs, notifications, native apps, agent-written parsers, source-discovery agents, a second model vendor, a hosted tracing service, other cities (the config allows it), Hoboken.

## Open decisions

1. Partnerships: whom to contact and in what order, once the idea is final. JC Families before their data is used; Cultural Affairs as a courtesy; the library needs no permission for its public feed.
2. Pin styles for city, business and community. Decided 2026-09-24: a pin shows what kind of event is on, not who runs it (`docs/design.md`, Icons).
3. v2 identity: named organizer only, or sign-in.
4. Geography: Hoboken.
5. Languages beyond English.
6. Merge policy for repair pull requests: a person merges the first five, then automatic if the gates hold, or never.

## Appendix: AGENTS.md draft

```
# JCMaps
Map of Jersey City events by time window. Static site + a Python pipeline run twice a day.
Read docs/brief.md when a decision needs context.

## Rules
- Feeds are parsed by code. Model calls are single functions: no tools, schema output,
  one vendor, all in pipeline/llm.py. Only code writes files or publishes.
- Every model-filled field carries an evidence quote; no quote means unknown.
- Fixtures are frozen under fixtures/<source>/; tests run offline.
  A step is done when its command passes.
- Log every model call to logs/llm.jsonl (input hash, output, model, tokens, cost, latency).
- Secrets live only in GitHub Actions; never in code, fixtures, prompts or logs.
- One module per source in pipeline/sources/<name>.py with fixtures/<name>/.
- Publishing goes through pipeline/gate.py; a failed gate keeps the last good snapshot and opens an issue.
- A prompt or model change is scored on fixtures/labeled/enrich.json before it replaces cached values.

## Commands
uv run jcmaps build [--source X]   # fetch, parse, geocode, enrich, check, publish
uv run jcmaps eval-enrich          # print 30 enriched events with quotes for a hand-check
uv run pytest                     # contract and search-rule tests, offline
python -m http.server -d site     # preview the frontend

## Layout
pipeline/   sources/, geocode.py, enrich.py, check.py, gate.py, publish.py, llm.py
fixtures/   frozen inputs per source; labeled/enrich.json is the labeled set
site/       index.html, app.js, data/events.json
docs/       brief.md, numbers.md
reports/    one JSON per run

## Not now
Database, accounts, submissions, agents in the pipeline, a second vendor, a tracing service, other cities.
```
