# JCMaps
Map of Jersey City events by time window. Static site + a Python pipeline run twice a day.
Read docs/brief.md when a decision needs context. Tickets are GitHub issues.

## Rules
- Feeds are parsed by code. Model calls are single functions: no tools, schema output,
  one vendor (OpenAI, gpt-6-luna unless JCMAP_MODEL says otherwise), all in pipeline/llm.py.
  Only code writes files or publishes.
- Every model-filled field carries an evidence quote; no quote means unknown.
- Fixtures are frozen under fixtures/<source>/; tests run offline. A step is done when its command passes.
- Git holds code, docs and fixtures. Generated files are never committed: site/data/ (snapshot,
  caches, latest report), reports/, logs/. The live site is the state between runs: a build starts
  with `--pull`, which fetches the previous deployment's snapshot and caches; a miss is a cold start,
  not lost data. Reports and logs are workflow artifacts (90 days).
- Secrets: the only one is OPENAI_API_KEY, an environment secret of `github-pages` (deploys from
  main only) in Actions and a git-ignored .env locally. Never in code, fixtures, prompts, logs or
  pull-request runs. The gate refuses to publish if anything under site/ looks like a key.
- Log every model call to logs/llm.jsonl (input hash, output, model, tokens, cost, latency).
- One module per source in pipeline/sources/<name>.py with fixtures/<name>/.
- Sources follow docs/sources.md: the organizer's own feed first, robots.txt and terms decide, no personal data,
  and some events never reach the map.
- Publishing goes through pipeline/gate.py; a failed gate keeps the last good snapshot and opens an issue.
- A prompt or model change is scored on fixtures/labeled/enrich.json (`jcmaps score-enrich`) before it replaces cached values.
- Search rules live once, in site/search.js (pure functions, no DOM); the browser runs them
  and tests/test_search.py runs their node tests.
- The look follows docs/design.md: colors, radii, shadows and the font are tokens in site/tokens.css, which
  every page loads (light only); nothing else names a color. Marigold (--accent) means an event, never a control.
- Commits: the person committing is the author and is responsible for the change. No AI co-author
  trailers (Co-authored-by: Claude or similar); AI assistance is disclosed once, in the README.
- Tickets use the Bug or Change template in .github/ISSUE_TEMPLATE; one ticket per pull request,
  and the pull request ticks the ticket's Done-when list, saying how each item was checked.
- Diagrams follow the code: when a pull request changes a workflow (the pipeline, the run, the page or the
  ticket process), it also updates the matching diagram in docs/how-it-works.md or docs/routine.md.

## Commands
uv run jcmaps build --pull [--source X] [--offline] [--no-model]   # pull live data, fetch, parse, enrich, check, publish
uv run jcmaps eval-enrich                                          # 30 enriched events with quotes for a hand-check
uv run jcmaps score-enrich                                         # the prompt and model on the labeled set: agreement per field, misses, cost
uv run pytest                                                      # contract, search-rule and design tests, offline (needs node)
python -m http.server -d site                                      # preview the frontend

## Layout
pipeline/   sources/, geocode.py, enrich.py, llm.py, check.py, gate.py, publish.py, cli.py
fixtures/   frozen inputs, one folder per adapter (library, tribe, ical); labeled/enrich.json is the labeled set
data/       library_branches.json (config)
site/       index.html, about.html, app.js, search.js, icons.js, visits.js, tokens.css; data/ is generated (events, enrich, geocode, report)
docs/       brief.md, numbers.md, design.md, how-it-works.md, routine.md, sources.md
city.json   boundary polygon, time zone, source list, site_url

## Not now
Database, accounts, submissions (the About page links to a Google Form that only the owner reads; nothing from it
reaches the pipeline), agents in the pipeline, a second vendor, a tracing service, other cities.
