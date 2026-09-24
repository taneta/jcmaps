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

## Notes

- Kid-friendly before the model: yes 148, no 10, unknown 335; after: yes 309, no 58, unknown 121. Price after: free 406, paid 6, unknown 76. Registration: yes 72, no 21. Every event has a summary; 195 carry the listing's own age wording.
- Prompt follow-ups for the first scored change: summarize from title and venue when a listing has no description; do not infer kid-friendly from a ceremony's title.
- Jersey City Connects' API says its timezone is UTC+0 while its times are local; the adapter treats wall time as Jersey City time.
- Deploy (step 6) waits for the GitHub repo; the hand-check (step 3) is done.
