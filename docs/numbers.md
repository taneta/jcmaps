# Numbers

The done-when column in the brief's day-one table is the prediction; this file records the outcome.

## Day one (2026-09-24)

| Number | Value |
|---|---|
| Events parsed per source | library 1183 (15 calendars, Learning Center empty), Cultural Affairs 66, Connects 38 |
| Events published (31-day horizon) | 488: library 411, Cultural Affairs 49, Connects 28 |
| Dropped | past 376, beyond horizon 390, closure notices 21, outside the city 6, duplicates 6 (Connects relisting library events) |
| Venues / with coordinates | 95 / 81; 94% of published occurrences have a pin (target was 95%; the misses are Bookmobile stops given as cross streets). The model located 9 offsite library events from their descriptions |
| Geocoder calls | 114 on the first run (Nominatim, one per second), 7 after enrichment found offsite venues, 0 afterwards |
| Wrong fields out of 30 hand-checked | 2 (kid-friendly on a flag-raising ceremony; a meta summary on a listing without a description), plus 2 borderline; no `no` and no `paid` without a quote. Corrected set frozen in fixtures/labeled/enrich.json |
| Cost per run | $0.072 for the first model run: 500 events became 305 distinct inputs (recurring programs share text), gpt-6-luna, 358K input and 75K output tokens, median 4.2 s per call, 0 errors. Later runs pay only for new events |
| Spot-check | 20 of 20 event pages show the title, date and start time the snapshot has |
| Build duration | 199 s on the first run (geocoding), 327 s for the first model run, 6 s when everything is cached |
| Snapshot size | 587 KB uncompressed (summaries and evidence included) |
| Tests | 24 (contract, search rules in node, checks, gate, enrichment, model-call glue) |
| Time spent | about 35 minutes of agent time, against a ten-hour budget |

## City prices, #16 (2026-09-24)

| Number | Value |
|---|---|
| City events with `price: unknown`, before | 43 of 48 (90%) in the live snapshot of 19:24 UTC |
| After the farmers market and street fair rule | 38 of 47 (81%) in a build from the feeds at 00:51 UTC on 25 September: the 4 Hamilton Park Farmers Market dates are free by rule |
| Still unknown | 18 showings of RENT at Art House and 20 one-off events; the city's feed leaves their cost empty and states no price we can quote (findings in #16) |

## Scrubbed fixtures, #55 (2026-09-25)

| Number | Value |
|---|---|
| Contact details in the frozen feeds | 60 distinct email addresses, 13 phone numbers and 510 iCal ORGANIZER lines in 8 files |
| Model input changed by the scrub | 240 of 614 frozen entries (39%): mostly library listings that name a branch's phone or email. The first run after the merge re-enriches that share of the live events once, about half of day one's model cost |

## Known points and street answers, #5 (2026-09-26)

| Number | Value |
|---|---|
| Known points | 15 in `data/venue_points.json`: the 13 library branches with an address, Art House Productions and Mary McLeod Bethune Park. 14 in use (the Learning Center's calendar is empty) |
| Pins after the rule, local rebuild from the live snapshot | 480 of 522 occurrences (92%), 65 of 81 venues. 14 from known points, 51 from place, building or amenity answers; none from a street answer to a query with a house number |
| Pins that moved | Cunningham branch 985 m and Bethune Park 1,455 m, from a street guess to the building; Art House 74 m (placed between 351 and 355 Marin Blvd, OSM has no 345); three others under 90 m from Nominatim's fresher answers |
| Unpinned venues, by events | City Hall Annex boardroom 5; 13 Bookmobile stops, most given as cross streets, 1 or 2 each; two venues outside the city or misspelled, 1 each |
| Geocoder calls in that rebuild | 61, refreshing the cache entries that lacked a category; 32 unused entries still lack one and are refreshed if a venue needs them |

## Weekly

`uv run jcmaps kpi --sample <file>` prints these from the live snapshot (docs/routine.md). Coverage is the KPI: the
share of a fixed weekly sample of Jersey City events, taken from places the map does not read, that the map shows.
The rest is health, as context: raw counts move with the season.

| Week | Events, next 7 days | Sources with events | Effective sources | Pinned | Price known | Coverage (sample) | Misses and why |
|---|---|---|---|---|---|---|---|
| 2026-W39, from Sept 26 | 147 (library 96, Connects 20, Cultural Affairs 16, city 5, Saint Peter's 5, Riverview 2, clinics 2, Barrow 1) | 8 | 2.2 | 95% | 76% | no sample yet | the first sample is next week's |

## Metrics

Events at a venue the geocoder could not place, tracked after every rebuild that changes pins and in the weekly
report read (`geocode.unpinned_events` in the run report; docs/routine.md). Events with no place at all (online,
or none given) are counted apart: nothing can pin them.

| Date | Events published | Venue without a pin | No place at all | What the unpinned are |
|---|---|---|---|---|
| 2026-09-24 | 488 | about 29, both kinds | | day one: Bookmobile stops given as cross streets |
| 2026-09-26 | 522 | 23 | 19 | after #5, local rebuild: 16 at 13 Bookmobile stops written as corners or descriptions (#83), 5 at the City Hall Annex boardroom, 2 outside the city or misspelled |
| 2026-09-26 | 492 | 16 | | the live run after #5 |
| 2026-09-26 | 544 | 22 | | the manual run after the day's sources landed (Saint Peter's, the county, the state clinics): 5 at the City Hall Annex, whose address the map service answers with a street (#86), the rest Bookmobile stops |

## Notes

- Kid-friendly before the model: yes 148, no 10, unknown 335; after: yes 309, no 58, unknown 121. Price after: free 406, paid 6, unknown 76. Registration: yes 72, no 21. Every event has a summary; 195 carry the listing's own age wording.
- Prompt follow-ups for the first scored change: summarize from title and venue when a listing has no description; do not infer kid-friendly from a ceremony's title.
- Jersey City Connects' API says its timezone is UTC+0 while its times are local; the adapter treats wall time as Jersey City time.
- Deployed 2026-09-24 to https://taneta.github.io/jcmaps/ from github.com/taneta/jcmaps. The first run crashed on an empty variable and opened its own issue; the second published 488 events with geocoding done on the runner (191 s cold). Model enrichment in Actions starts once the OPENAI_API_KEY secret exists.
- Moved to https://jcmaps.com/ the same day; the certificate was approved within a minute of setting the domain, and HTTPS is enforced. The github.io address redirects, and `--pull` follows the redirect.
