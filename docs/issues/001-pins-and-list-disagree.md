# 001: Pin counts, the list and the viewport disagree

Status: open. Found 2026-09-24 by Katerina on the local preview (Weekend, Everyone).
Move to a GitHub issue once the repo exists.

## Observed

1. A pin labelled "2" at Communipaw Branch; tapping it shows "1 event at Communipaw Branch".
2. With that pin the only one on screen, the sheet says "6 events in view".
3. After zooming out, a cluster shows "4" but the list does not change.

## Causes (verified against `site/data/events.json`)

**A. One place, several venue records.** A venue's id is a slug of name plus address, and the three
sources spell the same address differently, so Communipaw Branch exists three times at the same
coordinates:

| venue id | source | address text |
|---|---|---|
| communipaw-branch-295-johnston-ave-jersey-city-nj | library | 295 Johnston Ave, Jersey City, NJ |
| communipaw-branch-library-295-johnston-ave-jersey-city-07304 | culture | 295 JOHNSTON AVE., Jersey City, 07304 |
| communipaw-branch-295-johnston-ave-jersey-city-07304 | connects | 295 Johnston Ave, Jersey City, 07304 |

At street zoom the three pins sit exactly on top of each other. The "2" label belongs to the library
venue (two events); the tap landed on the Connects venue (one event), which turned red. Same problem for
902 Brewing, The Hutton, and the St. Joseph School for the Blind (a Bookmobile stop shares its address).

**B. One event, three listings.** "What We Keep" on Sat Sep 26 is listed by the library (1 to 5 PM),
Cultural Affairs ("What We Keep 2026", 1 to 5 PM) and Connects (2 to 4 PM). The duplicate rule needs
starts within 30 minutes and title similarity of 0.8, so neither pair merged: the Connects start is 60
minutes later, and the short title is a prefix of the long one.

**C. "In view" counts events that have no pin.** Events without coordinates are always listed, so the
header said 6 (four at the stacked Communipaw pins plus two unpinned) while the map showed one pin.

**D. A selected pin freezes the list.** After a pin is tapped the list only follows that venue, and
`moveend` skips re-rendering while a venue is selected, so zooming out changed the map but not the list.
The only way out is the small "clear pin ×" in the header.

## Plan

1. **Venue identity by normalized address** (`pipeline/geocode.py`): key a venue on house number plus
   street name (lowercase, "avenue" to "ave", "street" to "st", punctuation dropped), falling back to the
   name when there is no address. Records that share a key merge into one venue; other names go to
   `aliases`. Name preference: fixed library branch names, then other sources, then Bookmobile stop
   labels last. Test: the three Communipaw records become one venue with two aliases; Bethune Park
   (43 MLK Dr) and the Cunningham amphitheater (275 MLK Dr) stay separate even though they geocoded to
   the same point.
2. **Looser duplicate rule** (`pipeline/check.py`): same venue key, same date, overlapping times, and
   either title similarity of 0.8 or one normalized title starting with the other's first three words.
   The record with more evidence still wins and keeps every URL. Test: the three "What We Keep"
   listings become one event with two `alt_urls`.
3. **List logic as a pure function** (`site/search.js`): `listFor(results, bounds, venueId)` returns
   `{inView, unpinned}`. The header counts only pinned events inside the viewport; unpinned events sit
   under their own heading "No map pin (n)". Node tests cover both.
4. **Selection that lets go** (`site/app.js`): tapping a pin filters to that venue and the header shows
   the venue name with a clear button; any drag, zoom, or tap on empty map clears the selection and the
   list follows the viewport again. With one venue per place, the pin label equals the number of cards.
5. Rebuild, check the three screens from the report on the phone viewport, then close this ticket.

Estimate: about two hours. Follow-up noted, not in scope: Nominatim resolved two different MLK Drive
addresses to one point; consider rejecting results that are not a building or address match.

## Acceptance

- No two venues in the snapshot share a normalized address key (test on the venue table).
- Tapping any pin lists exactly as many events as its label says, in the current view.
- The header count equals the number of cards above the "No map pin" section.
- Zooming or panning after a tap updates the list.
- `uv run pytest` passes, including the new node tests.
