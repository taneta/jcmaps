# JCMaps

A map of Jersey City events by time window: what is on today, tomorrow, at the weekend or on the dates you pick,
with a family view by default. Non-commercial. Data comes from the public feeds of the Jersey City Free Public
Library, the Office of Cultural Affairs and Jersey City Connects, rebuilt twice a day by GitHub Actions and served
as a static page from GitHub Pages at https://jcmaps.com/.

- `docs/brief.md` is the product brief; `AGENTS.md` holds the build rules for anyone (or any agent) working here.
- New here? Read `docs/how-it-works.md` (the pieces, in two diagrams) and `docs/routine.md` (who does what, and when).
- `uv run jcmaps build --pull` runs the pipeline; `uv run pytest` runs the offline tests; `python -m http.server -d site` previews the page.
- Events show a "Report a problem" link that opens a prefilled issue.
- Built with AI assistance; every change is reviewed by a person, who is responsible for it.

## How it runs

- **One path for every trigger.** Schedule (2am and 7am), a push to `main`, or a manual run all do the same
  thing: pull the live site's `data/events.json` and caches, fetch the feeds, enrich new events, run the checks
  and the gate, deploy the `site/` folder to Pages. If the gate fails, the pulled snapshot is republished
  unchanged and an issue opens, so the site never goes dark.
- **Nothing generated is committed.** The repo holds code, docs and frozen fixtures. The current data lives
  on the site; run reports and model logs are workflow artifacts kept for 90 days.
- **Local runs** use `.env` (git-ignored) for `OPENAI_API_KEY`; without a key, enrichment falls back to the
  adapter rules and whatever is cached. `--offline` builds from fixtures alone.

## Secrets and safety

- The only secret is the OpenAI key. In GitHub it is an environment secret of `github-pages`, which deploys
  from `main` only; it is never available to pull-request runs. Use a dedicated OpenAI project with a monthly
  budget cap and a key restricted to model requests, so a leak costs at most the cap.
- Rotation: revoke the key at OpenAI, create a new one, paste it into the environment secret. Nothing else changes.
- Push protection (secret scanning) is on for the repo; the gate also refuses to publish if anything under
  `site/` looks like a key.
- Settings knobs are repository variables: `JCMAP_MODEL` (default `gpt-6-luna`), `JCMAP_EFFORT` (`low`),
  `JCMAP_COST_CAP_USD` (`5`).

## When an issue opens

The build opens an `auto:build` issue when the gate fails or a source returns nothing. The issue body carries
the run report; the full log is in the run's artifact. Fix the adapter or the source, refreeze the fixture
if the feed changed shape, and re-run the workflow.
