# Design guide

The look of JC Maps: a quiet map, warm neutral surfaces and one sunny color, marigold, for events. The values live in
the `:root` block of `site/tokens.css`, which both pages load; this file says what each is for and how to use it.
`tests/test_design.py` checks what a machine can check. Read this before changing anything under `site/`.

## Principles

1. **The map is the content.** Surfaces are warm neutrals and the basemap is muted, so the pins carry the color.
2. **Color means event.** Marigold marks events and nothing else: pins, clusters, the small pin before a card's time,
   the selected card, the app icon. Controls are ink: a pressed chip is dark on light.
   Selection highlights and never recolors: a selected pin grows and glows.
3. **Facts are solid, unknowns are dashed.** A filled tag states something from the listing; a dashed outline says
   the listing does not state it. This is the brief's "evidence or unknown" rule, made visible.
4. **One source for every value.** Colors, radii, shadows and the font are tokens, and everything else refers to them.
   `app.js` reads tokens with `token(name)` and never names a color.
5. **Phone first, light only.** The page stays light even when the system is dark, because dark maps are hard to
   read (see Not now). Tap targets are 44px; fields use 16px text, because iOS zooms into anything smaller.

## Color

| Token | Used for | Value |
|---|---|---|
| `--surface` | sheet, chips, map controls, banner text, count badges on pins | `#FFFFFF` |
| `--surface-2` | fact tags, section headings | `#F4F1EC` |
| `--ink` | titles, pressed controls, the banner, focus ring, numbers on count badges | `#1E1B17` |
| `--ink-2` | summaries, links, unpressed segments | `#534D45` |
| `--ink-3` | venue, hints, footer, unknown tags, map place names | `#736B61` |
| `--line` | dividers, the ring around the sheet | `#EAE6E0` |
| `--line-strong` | field borders, dashed tags, the grip | `#958C81` |
| `--accent` | pins, clusters, the glow, the small pin on a card, the app icon: marigold | `#FFB627` |
| `--accent-edge` | the thin ring around pins, clusters, count badges and the small pin | `#B27200` |
| `--accent-tint` | the selected card | `#FFF3D6` |
| `--on-accent` | numbers on clusters, icons on pins and cards | `#1E1B17` |
| `--free-bg` / `--free-text` | the Free tag | `#E3F0DA` / `#2D6526` |
| `--kids-bg` / `--kids-text` | the Kids tag | `#EDE7FA` / `#5A3DA6` |
| `--map-land` | land, the page behind the map, theme-color | `#F3F0EA` |
| `--map-water` | water | `#C9DAE3` |
| `--map-park` | parks and woods | `#DDE6D2` |
| `--map-building` | buildings | `#E8E3DA` |

- **Contrast.** Text meets 4.5:1 and field borders 3:1 against what they sit on. A pin's fill or ring
  meets 3:1 against land and parks; venues are addresses, so pins never sit on water. The text pairs are listed in
  `PAIRS` in the test; a new pairing gets a line there.
- **Why marigold, not red.** Red read as an alert; the map should feel like a sunny day out. Marigold sits between
  sunflower (too pale on the light map) and tangerine (closer to a warning).
- **Why yellow needs a ring and dark numbers.** Marigold is light, so on the light map it barely differs from the land
  (1.5:1). A thin `--accent-edge` ring gives each pin its outline (3.5:1 on land, 3.1:1 in parks). It is the lightest
  amber that still does, so it stays a soft tonal edge rather than an outline. Numbers and icons on marigold are ink
  (9.8:1), never white. Yellow text is unreadable on white, so a card's time is ink with a small marigold pin in front.
- **Why the banner is ink.** An amber warning would look like an event, so the stale-data banner is inverted instead:
  `--ink` background, `--surface` text.
- **Why Free is green and Kids is violet.** They mirror the two filters people use most, Free and Family. Every
  other tag is neutral, and a new tag stays neutral unless it mirrors a filter.
- **Format.** Six-digit uppercase hex. MapLibre reads the map tokens and does not understand `oklch()` or `color-mix()`.
- **Adding a color** means a token in `:root`, a row in this table and its pairs in the test.

## Type

One font: `--font`, the system stack (San Francisco on Apple devices, Roboto on Android, Segoe UI on Windows). There is
nothing to download and it looks native.

| Size | Weight | Used for |
|---|---|---|
| 20px | 600 | the About page's title |
| 16px | 400 to 600 | card title and sheet count (600); inputs (500); the About page's text (400) |
| 14px | 400, 500 | venue, summary, banner (400); chips and segments (500) |
| 13px | 400 to 600 | type and time on a card (600), links (500), hints and the Free note (400) |
| 12px | 400 to 600 | footer (400), tags (500), section headings (600, uppercase, 0.06em tracking) |

Line height is 1.45 for text (1.5 for the About page's paragraphs) and 1.3 for titles. There are no other sizes and
nothing heavier than 600. Times and counts use tabular numerals, so they line up.

## Space, shape, depth

- **Spacing.** 12px from the screen edge to floating controls, 16px inside the sheet. 8px between chips, 6px
  between tags, 20px between links. A card has 14px top and bottom and 16px at the sides, with 2px between time,
  title and venue, 6px before the summary and 10px before tags and links.
- **Radius.** `--radius-pill` for chips, tags, fields and the grip; `--radius-md` (12px) for map controls and the
  banner; `--radius-lg` (20px) for the sheet and for the About page on a wide screen.
- **Depth.** Two shadows: `--shadow-float` for everything over the map (chips, banner, map controls, credits)
  and for the About page's column, and `--shadow-sheet` for the sheet. Both include a 1px ring, so edges hold on any
  part of the map.

## Components

- **Time chips** (`#windows .chip`): 36px pills, 14px/500, ink on surface; pressed is an ink fill with surface text.
  One is always pressed, Today by default. The four (Today, Tomorrow, Weekend, Dates) fit on one line at 375px;
  "Dates" is short so that they do. A narrower phone scrolls the row sideways and brings the pressed chip into view.
- **Segmented control** (`.seg`, Family | Everyone): one pill holding two buttons; the chosen one is ink. Use it for
  a choice between two named states, never a single button whose label flips.
- **Toggle chip** (Free): a chip with `aria-pressed`, looking like a time chip.
- **Field chip** (From, To, under Dates): a `label.chip` around its date input, so the label text names it. The
  input has no border of its own, because the chip is its frame.
- **Text button** (for example, clearing a selected pin): 14px/600 in `--ink-2`, no fill, 44px tall. Never `--accent`.
- **Banner** (`#banner`): inverted, `--surface` text on `--ink`, with a 12px radius and the float shadow, inside the
  12px margins. It is for stale data only; a failed load says so in the list.
- **Sheet**: surface, 20px top corners, a grip (phones only), and a handle row with the count (16px/600), a hint
  (13px, `--ink-3`) and, while a pin is selected, the Clear text button. On a phone it covers 42% of the height, 88%
  expanded, or the handle row alone: it follows a finger on the handle and settles at the nearest of the three, and a
  tap toggles the first two. From 900px wide it is a 420px panel floating on the right, 16px from the edges.
- **Event card**: a 20px marigold pin with the event's icon (12px, `--on-accent`), 8px before the type's name and the
  time (13px/600, `--ink-2`): "Art and crafts · Sat, Sep 26 · 9:30–11 AM". A card of unknown type has the pin without
  an icon and no name. Then the title (16px/600), venue and organizer (`--ink-3`), summary (`--ink-2`), tags and
  links. Selected: `--accent-tint` background. The card is one tap target, and each link is its own.
- **Tags**: 12px/500 pills. A fact (price text, ages, Registration) is `--surface-2` with `--ink-2`; Free and Kids
  use their own colors. An unknown (kids: not stated, price not listed) is a dashed
  `--line-strong` outline with `--ink-3` text.
- **Links**: 13px/500, underlined in `--line-strong`; "Source ↗" in `--ink-2`, "Report on GitHub" in `--ink-3`,
  both full ink on hover.
- **Note** (what Free left out): while Free is on, the first row of the list says how many events it left out for
  not listing a price ("9 more don't list a price"), counted where the list counts events. 13px `--ink-3` on
  `--surface-2`, full width, with a `--line` below. Free stays strict and says so, rather than hiding quietly.
- **Section heading** (Ongoing, No map pin): 12px/600 uppercase in `--ink-3` on `--surface-2`.
- **Empty state and footer**: `--ink-3`; the empty state is centered, the footer 12px. The footer ends with a link
  to the About page in `--ink-2`.
- **Credits** (`.credits`): one line under "locate me", "About JC Maps · © OpenMapTiles · © OpenStreetMap ⓘ", 12px
  `--ink-3` on `--surface` with the float shadow and a 12px radius. About JC Maps comes first, in `--ink-2` at 500:
  it is the way to the About page, and it never folds. The two credits show when the map opens and fold behind ⓘ at
  the first pan, zoom or tap; ⓘ brings them back.
- **About page** (`site/about.html`): one column of reading text, 640px at most: 16px/400 `--ink` at 1.5 line height,
  20px from the screen's edges on a phone, headings styled as section headings, links underlined in `--line-strong`.
  On a phone the column is the whole page in `--surface`; from 700px wide it floats on `--map-land` with a 20px radius
  and the float shadow. "Back to the map" is a text button. The source suggestion is a `--surface-2` panel holding the
  page's one button: an ink pill, 44px tall, with `--surface` text, like a pressed chip. Never marigold, because a
  suggestion is not an event.
- **App icon** (`site/icon.svg`, also the favicon): Jersey City's strip of land (`--map-land`) between the
  Hackensack and the Hudson (`--map-water`), with the pin on it glowing, drawn as a selected pin on the map. It has
  no teardrop pin, and it never puts ink on yellow: yellow and black read as a taxi brand. Its colors are pale,
  so at 16px in a browser tab the pin carries the icon.

## Map

- **Basemap.** OpenFreeMap's `positron`. `tintBasemap()` in `app.js` paints land, water, parks and buildings with the
  `--map-*` tokens, softens place names to `--ink-3` and hides route-number shields. It matches layers by type and
  source layer rather than by id, so a style update leaves a new layer untinted instead of breaking the page.
- **Pins.** `--accent` circles of 14px radius with a 1.5px `--accent-edge` ring and one icon (16px, `--on-accent`)
  chosen as in Icons below. A pin with more than one event carries the count on a badge on its top-right edge:
  `--surface` with a 1px `--accent-edge` ring and the number in `--ink`, Noto Sans Bold 11px, from OpenFreeMap's
  glyphs. The count tells whether a tap shows one event or several.
- **Clusters.** Drawn like pins, 16, 20 or 25px, with a 13px count in the middle and no icon; the number in the
  middle tells a cluster from a pin.
- **Selected venue.** Highlighted, never recolored: the pin grows by 4px and its icon to 20px, its ring thickens to
  2.5px, and a soft marigold glow (80%, blurred, 16px beyond the pin) lies beneath it. On the map, a glow means
  "selected" and nothing else.
- **Controls.** MapLibre's own controls, restyled: 44px buttons in a 12px-radius group with the float shadow. A phone
  shows only "locate me", above the sheet on the right, within reach of a thumb, with the credits under it; a mouse
  also gets zoom buttons. On desktop, the controls and the credits sit left of the sheet.
- **Credits.** Our credits line (Components) replaces MapLibre's attribution control, whose default line named three
  "Open" projects. OpenStreetMap's guidelines want their credit in a corner of the map, linked to its copyright page
  and visible when the map opens; it may fold on the first pan, zoom or tap if an info button brings it back.
  OpenMapTiles also wants its credit in the map's corner. Neither may move to another page. OpenFreeMap asks for no
  credit on the map, so the About page thanks it instead. The text is written in `app.js`, not read from the style:
  a new basemap source needs its credit added there.
- **No pin styles by organizer type** (open decision 2 in the brief, closed by Icons): one mark per pin is enough,
  and what is on matters more than who runs it.

## Icons

One icon on each pin says what is on there, and each card in the list starts with its event's icon and the type's
name. The icons are Phosphor Icons 2.1 (MIT license, fill weight), kept as SVG paths in `site/icons.js` with the
license notice: nothing to download, painted with `--on-accent`, never a new color.

| Type | Icon | Name on a card | For example |
|---|---|---|---|
| `festivals` | confetti | Festivals | festivals, parades, block parties |
| `markets` | storefront | Markets and fairs | farmers markets, fairs, sales, swaps |
| `stories` | book-open | Stories and books | storytimes, book clubs, poetry, Bookmobile stops |
| `games` | puzzle-piece | Games | bingo, chess, board games, trivia, Lego |
| `shows` | mask-happy | Shows and films | theater, puppet shows, comedy, movies |
| `music` | music-notes | Music and dance | concerts, karaoke, salsa, dance classes |
| `health` | heartbeat | Health and sport | yoga, run clubs, vaccine clinics |
| `crafts` | palette | Art and crafts | crafts, painting, sewing, exhibitions |
| `classes` | graduation-cap | Classes and talks | languages, tech help, talks, workshops |
| `meetups` | users-three | Meetups | mixers, speed dating, volunteering |

- **The icon on a pin**, from its events in view (the ones its badge counts): the type they share. When they are of
  several types, the place's own icon, or a calendar (`calendar-dots`) for a place without one. Events of unknown
  type do not count, and a pin whose events are all unknown stays plain. One rule for every place:
  `pinIcons()` in `site/search.js`.
- **Place icons** belong to a `Venue.kind` in `PLACES` in `site/icons.js`: today only `library`, the columned building
  (`bank`), which is what the main library looks like. A kind of place gets an icon when it regularly hosts several
  kinds of events. On most maps the columned building means a museum; if museums arrive, the library can take books
  on a shelf (`books`).
- **Where a type comes from.** Code, never the model: `type_of()` in `pipeline/enrich.py` takes the first type whose
  words are in the title, else the first of the feed's own categories that names one, and keeps the matched words as
  evidence. Nothing matched is `unknown`. The order settles overlaps: a festival with a band is a festival, musical
  bingo is a game. About 92% of events had a type on 2026-09-24.
- **In the list**, a card shows its own event's icon whatever the pin shows, and the type's name next to it, so the list
  reads by kind without learning the icons. The icon is `aria-hidden`; the name says it.
- **Adding a type** means a line in `EventType` and `TITLE_WORDS` in the pipeline and an icon and a name in
  `site/icons.js`, all in the same order; `test_every_type_has_an_icon_and_a_name` keeps them together.

## Accessibility

- Contrast as above, checked by the test.
- Focus: a 2px ink outline, offset 2px, through `:focus-visible`.
- Tap targets are 44px: chips and links draw smaller and extend their target with `::before`.
- State lives in the markup: `aria-pressed` on chips and segments, and the CSS styles the attribute, so what the
  control says and what it shows cannot drift apart.
- Motion: the sheet's 200ms height change is the only animation, and `prefers-reduced-motion` turns it off. MapLibre
  skips its fly-to animation under the same setting.
- Color never carries meaning alone: Free and Kids are words, unknown tags also differ by outline, and a selected
  pin also grows and changes the list heading to "N events at" the venue. An icon never stands alone either: every
  card names its type.

## Where the values live

| Place | Holds | Kept in step by |
|---|---|---|
| `site/tokens.css`, the `:root` block | every token; both pages load it | this file |
| `site/index.html` and `site/about.html`, in `<style>` | `var()` references only | `test_colors_are_tokens` |
| `site/app.js` | token names, read at load for the map and its icons | `test_colors_are_tokens` |
| `site/icons.js` | icon paths, type names, place icons; no colors | `test_every_type_has_an_icon_and_a_name` |
| `pipeline/enrich.py`, `TITLE_WORDS` and `CATEGORY_WORDS` | the words that decide a type | `tests/test_enrich.py` |
| `<meta name="theme-color">`, in both pages | `--map-land` | `test_copies_match_tokens` |
| `site/manifest.webmanifest` | `--map-land` | `test_copies_match_tokens` |
| `site/icon.svg` | palette colors only, `--accent` among them | `test_copies_match_tokens` |

## Changing the design

Change the token, not the component. Run `uv run pytest`, then look at the page at phone width and on desktop.
A new component uses the existing tokens; a new token is a decision, recorded here with its reason.

Not now: web fonts, icons beyond the ones in Icons, illustrations, animation beyond the sheet, and a dark theme. The dark theme came out
on 2026-09-24 because dark maps are hard to read. Its tokens and the dark map tinting are in the history of #10; if
it comes back, it first needs a map that stays legible at night.
