# Design guide

The look of JC Maps: a quiet map, warm neutral surfaces and one sunny color, marigold, for events. The values live in
the two `:root` blocks at the top of `site/index.html`; this file says what each is for and how to use it.
`tests/test_design.py` checks what a machine can check. Read this before changing anything under `site/`.

## Principles

1. **The map is the content.** Surfaces are warm neutrals and the basemap is muted, so the pins carry the color.
2. **Color means event.** Marigold marks events and nothing else: pins, clusters, the dot before a card's time, the
   selected card, the app icon. Controls are ink: a pressed chip is dark on light (light on dark in the dark theme).
   Selection highlights and never recolors: a selected pin grows and glows.
3. **Facts are solid, unknowns are dashed.** A filled tag states something from the listing; a dashed outline says
   the listing does not state it. This is the brief's "evidence or unknown" rule, made visible.
4. **One source for every value.** Colors, radii, shadows and the font are tokens, and everything else refers to them.
   `app.js` reads tokens with `token(name)` and never names a color.
5. **Phone first, both themes.** Every color has a light and a dark value, and the theme follows the system. Tap
   targets are 44px; fields use 16px text, because iOS zooms into anything smaller.

## Color

| Token | Used for | Light | Dark |
|---|---|---|---|
| `--surface` | sheet, chips, map controls, banner text | `#FFFFFF` | `#1B1916` |
| `--surface-2` | fact tags, section headings | `#F4F1EC` | `#26231F` |
| `--ink` | titles, pressed controls, the banner, focus ring | `#1E1B17` | `#F2EEE8` |
| `--ink-2` | summaries, links, unpressed segments | `#534D45` | `#CFC7BC` |
| `--ink-3` | venue, hints, footer, unknown tags, map place names | `#736B61` | `#A0978B` |
| `--line` | dividers, the ring around floating things in dark | `#EAE6E0` | `#332F29` |
| `--line-strong` | field borders, dashed tags, the grip | `#958C81` | `#716960` |
| `--accent` | pins, clusters, the glow, the dot on a card, the icon: marigold | `#FFB627` | `#FFB627` |
| `--accent-edge` | the thin ring around pins, clusters and the dot | `#B27200` | `#B27200` |
| `--accent-tint` | the selected card | `#FFF3D6` | `#33290F` |
| `--on-accent` | numbers on pins and clusters | `#1E1B17` | `#1E1B17` |
| `--free-bg` / `--free-text` | the Free tag | `#E3F0DA` / `#2D6526` | `#1E2D1B` / `#9FD18F` |
| `--kids-bg` / `--kids-text` | the Kids tag | `#EDE7FA` / `#5A3DA6` | `#2A2440` / `#C4B5F4` |
| `--map-land` | land, the page behind the map, theme-color | `#F3F0EA` | `#100F0D` |
| `--map-water` | water | `#C9DAE3` | `#1A2830` |
| `--map-park` | parks and woods | `#DDE6D2` | `#1B271B` |
| `--map-building` | buildings | `#E8E3DA` | `#211F1B` |

- **Contrast.** Text meets 4.5:1 and field borders 3:1 against what they sit on, in both themes. A pin's fill or ring
  meets 3:1 against land and parks; venues are addresses, so pins never sit on water. The text pairs are listed in
  `PAIRS` in the test; a new pairing gets a line there.
- **Why marigold, not red.** Red read as an alert; the map should feel like a sunny day out. Marigold sits between
  sunflower (too pale on the light map) and tangerine (closer to a warning).
- **Why yellow needs a ring and dark numbers.** Marigold is light, so on the light map it barely differs from the land
  (1.5:1). A thin `--accent-edge` ring gives each pin its outline (3.5:1 on land, 3.1:1 in parks). It is the lightest
  amber that still does, so it stays a soft tonal edge rather than an outline. The numbers are ink (9.8:1), never
  white. Yellow text is unreadable on white, so a card's time is ink with a marigold dot in front.
- **Why the banner is ink.** An amber warning would look like an event, so the stale-data banner is inverted instead:
  `--ink` background, `--surface` text.
- **Why Free is green and Kids is violet.** They mirror the two filters people use most, Free and Family. Every
  other tag is neutral, and a new tag stays neutral unless it mirrors a filter.
- **Format.** Six-digit uppercase hex. MapLibre reads the map tokens and does not understand `oklch()` or `color-mix()`.
- **Adding a color** means a token in both `:root` blocks, a row in this table and its pairs in the test.

## Type

One font: `--font`, the system stack (San Francisco on Apple devices, Roboto on Android, Segoe UI on Windows). There is
nothing to download and it looks native.

| Size | Weight | Used for |
|---|---|---|
| 16px | 500, 600 | card title and sheet count (600); inputs (500) |
| 14px | 400, 500 | venue, summary, banner (400); chips and segments (500) |
| 13px | 400 to 600 | time on a card (600), links (500), hints (400) |
| 12px | 400 to 600 | footer (400), tags (500), section headings (600, uppercase, 0.06em tracking) |

Line height is 1.45 for text and 1.3 for titles. There are no other sizes and nothing heavier than 600. Times and
counts use tabular numerals, so they line up.

## Space, shape, depth

- **Spacing.** 12px from the screen edge to floating controls, 16px inside the sheet. 8px between chips, 6px
  between tags, 20px between links. A card has 14px top and bottom and 16px at the sides, with 2px between time,
  title and venue, 6px before the summary and 10px before tags and links.
- **Radius.** `--radius-pill` for chips, tags, fields and the grip; `--radius-md` (12px) for map controls and the
  banner; `--radius-lg` (20px) for the sheet.
- **Depth.** Two shadows: `--shadow-float` for everything over the map (chips, banner, map controls, attribution)
  and `--shadow-sheet` for the sheet. Both include a 1px ring, so edges hold on any part of the map; the dark theme
  relies on the ring, because shadows barely show on dark.

## Components

- **Time chips** (`#windows .chip`): 36px pills, 14px/500, ink on surface; pressed is an ink fill with surface text.
  One is always pressed. On a phone the row scrolls sideways and brings the pressed chip into view.
- **Segmented control** (`.seg`, Family | Everyone): one pill holding two buttons; the chosen one is ink. Use it for
  a choice between two named states, never a single button whose label flips.
- **Toggle chip** (Free): a chip with `aria-pressed`, looking like a time chip.
- **Field chip** (Age, From, To): a `label.chip` around its input, so the label text names it. Number fields get a
  pill border; date fields have none, because the chip is their frame.
- **Text button** (for example, clearing a selected pin): 14px/600 in `--ink-2`, no fill, 44px tall. Never `--accent`.
- **Banner** (`#banner`): inverted, `--surface` text on `--ink`, with a 12px radius and the float shadow, inside the
  12px margins. It is for stale data only; a failed load says so in the list.
- **Sheet**: surface, 20px top corners, a grip (phones only), and a handle row with the count (16px/600), a hint
  (13px, `--ink-3`) and, while a pin is selected, the Clear text button. On a phone it covers 42% of the height, or
  88% expanded. From 900px wide it is a 420px panel floating on the right, 16px from the edges.
- **Event card**: time (13px/600, `--ink-2`) after an 8px marigold dot, which is the pin in small; then the title
  (16px/600), venue and organizer (`--ink-3`), summary (`--ink-2`), tags and links. Selected: `--accent-tint`
  background. The card is one tap target, and each link is its own.
- **Tags**: 12px/500 pills. A fact (price text, ages, Registration) is `--surface-2` with `--ink-2`; Free and Kids
  use their own colors. An unknown (kids: not stated, price not listed, ages not stated) is a dashed
  `--line-strong` outline with `--ink-3` text.
- **Links**: 13px/500, underlined in `--line-strong`; "Source ↗" in `--ink-2`, "Report a problem" in `--ink-3`,
  both full ink on hover.
- **Section heading** (Ongoing, No map pin): 12px/600 uppercase in `--ink-3` on `--surface-2`.
- **Empty state and footer**: `--ink-3`; the empty state is centered, the footer 12px.
- **App icon** (`site/icon.svg`, also the favicon): Jersey City's strip of land (`--map-land`) between the
  Hackensack and the Hudson (`--map-water`), with the pin on it glowing, drawn as a selected pin on the map. It has
  no teardrop pin, and it never puts ink on yellow: yellow and black read as a taxi brand. The day colors are pale,
  so at 16px in a browser tab the pin carries the icon.

## Map

- **Basemap.** OpenFreeMap's `positron`, or `dark` when the system is dark, chosen once at page load: a theme change
  shows on the next visit. `tintBasemap()` in `app.js` paints land, water, parks and buildings with the `--map-*`
  tokens, softens place names to `--ink-3` and hides route-number shields. It matches layers by type and source
  layer rather than by id, so a style update leaves a new layer untinted instead of breaking the page.
- **Pins.** `--accent` circles with a 1.5px `--accent-edge` ring, 9, 12 or 15px as the event count grows. Counts above
  one are in `--on-accent`, Noto Sans Bold 11px, from OpenFreeMap's glyphs.
- **Clusters.** Drawn like pins, 16, 20 or 25px, with a 13px count; their size tells them apart.
- **Selected venue.** Highlighted, never recolored: the pin grows by 4px, its ring thickens to 2.5px and its count to
  13px, and a soft marigold glow (80%, blurred, 16px beyond the pin) lies beneath it. On the map, a glow means
  "selected" and nothing else.
- **Controls.** MapLibre's own controls, restyled: 44px buttons in a 12px-radius group with the float shadow, and
  icons inverted in the dark theme. A phone shows only "locate me", above the sheet on the right, within reach of a
  thumb; a mouse also gets zoom buttons. On desktop, the controls and the attribution sit left of the sheet. The
  OpenStreetMap attribution stays visible: the license requires it.
- **Pin styles by organizer type** (open decision 2 in the brief): if they come, vary the shape or the ring, not the
  color, so that color keeps meaning "event".

## Accessibility

- Contrast as above, checked by the test.
- Focus: a 2px ink outline, offset 2px, through `:focus-visible`.
- Tap targets are 44px: chips and links draw smaller and extend their target with `::before`.
- State lives in the markup: `aria-pressed` on chips and segments, and the CSS styles the attribute, so what the
  control says and what it shows cannot drift apart.
- Motion: the sheet's 200ms height change is the only animation, and `prefers-reduced-motion` turns it off. MapLibre
  skips its fly-to animation under the same setting.
- Color never carries meaning alone: Free and Kids are words, unknown tags also differ by outline, and a selected
  pin also grows and changes the list heading to "N events at" the venue.

## Where the values live

| Place | Holds | Kept in step by |
|---|---|---|
| `site/index.html`, the two `:root` blocks | every token | this file |
| `site/index.html`, everything else in `<style>` | `var()` references only | `test_colors_are_tokens` |
| `site/app.js` | token names, read at load for the map | `test_colors_are_tokens` |
| `<meta name="theme-color">`, light and dark | `--map-land` | `test_copies_match_tokens` |
| `site/manifest.webmanifest` | `--map-land`, light | `test_copies_match_tokens` |
| `site/icon.svg` | palette colors only, `--accent` among them | `test_copies_match_tokens` |

## Changing the design

Change the token, not the component. Run `uv run pytest`, then look at the page at phone width in both themes.
A new component uses the existing tokens; a new token is a decision, recorded here with its reason.

Not now: web fonts, an icon set, illustrations, animation beyond the sheet, a theme switch on the page (the system
decides), and switching the map's theme without a reload.
