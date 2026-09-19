# Summoner Trends

A League of Legends match analytics pipeline. It pulls match data from the
official Riot Games API, lands it in DuckDB, and transforms it with dbt into
analytics-ready tables that show **how a player's performance trends over time**.

This is a personal portfolio project, built to practice extraction, warehouse
modelling, testing, and CI on a dataset I actually care about.

## What it does (and deliberately does not do)

Summoner Trends is **descriptive**. It answers questions like:

- How has my CS/min moved over my last 50 ranked games?
- Is this game's damage share unusual compared to my own history?
- Which champions are picked and banned most on the current patch?

It is **not** a grading or rating system. There is no skill rating, no MMR or
ELO estimate, and no letter grades. Player-level output stays neutral and
statistical — trend lines, rolling averages, percentiles, and z-scores against
a player's own history — never an evaluative label or verdict about a player.

## Riot API policy constraints

These are design constraints, not suggestions. They shaped the model layer and
should be respected by anything added later:

- **No alternate ranking or grading system.** No custom skill rating, MMR, ELO
  calculation, or S/A/B/C/D/F grades derived from the data. This was
  deliberately dropped from the design and should not be reintroduced.
- **No player evaluation or shaming.** Player-level stats stay descriptive.
  Comparisons are to the player's own baseline, expressed as percentiles and
  z-scores, not as judgements about the player.
- **Official sources only.** Data comes from documented Riot API endpoints and
  from Data Dragon / Community Dragon static data. No scraping of undocumented
  endpoints or third-party sites.
- **The API key is never committed.** It lives in `.env`, which is gitignored.
  `.env.example` documents the variables without carrying a real key.
- **Rate limits are respected.** Extraction is built around a Personal key
  (20 requests/second, 100 requests/2 minutes, per region) with 429 handling
  that honours `Retry-After` and exponential backoff.

Summoner Trends isn't endorsed by Riot Games and doesn't reflect the views or
opinions of Riot Games or anyone officially involved in producing or managing
Riot Games properties.

## Stack

| Layer | Tool |
| --- | --- |
| Extraction | Python (`requests`, custom rate limiter + backoff) |
| Warehouse | DuckDB |
| Transformation | dbt (`dbt-duckdb`) |
| CI | GitHub Actions — `dbt build` plus tests on every push |

## Layout

```
summoner-trends/
├── extraction/          Python: Riot API clients (Account-V1, Summoner-V4,
│                        Match-V5, Champion-Mastery-V4), rate limiting, loader
├── models/
│   ├── staging/         One model per raw source: type casting, renaming
│   ├── intermediate/    Joins and derived fields (KDA, gold efficiency, ...)
│   └── marts/           Analytics-ready fact and dimension tables
├── snapshots/           Slowly changing data (champion balance across patches)
├── macros/              Reusable dbt macros
├── tests/               Custom singular dbt tests
├── seeds/               Small static reference CSVs
├── ci/                  Fixture generator so CI can build without the API
└── .github/workflows/   CI
```

## Data model

**Dimensions**

- `dim_champions` — champion reference data from Data Dragon.
- `dim_players` — one row per tracked account (PUUID, Riot ID, platform).
- `dim_matches` — one row per match: queue, patch, duration, map.

**Facts**

- `fct_participant_performance` — one row per player per match: KDA, damage
  share, gold efficiency, CS/min, vision score, kill participation, game
  duration, result.
- `fct_player_rolling_trends` — rolling averages and percentiles of those
  metrics across a player's match history. Powers the trend lines.
- `fct_player_match_deltas` — each match's stats relative to that player's own
  historical baseline (z-score and percentile rank). Descriptive statistical
  analysis, not an evaluation.
- `fct_champion_meta` — aggregate win rate, pick rate, and ban rate by champion
  by patch.

## Getting started

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env: add your Riot API key and Riot ID

# 1. extract
python -m extraction.pull_matches --count 100

# 2. transform
dbt deps --profiles-dir .
dbt build --profiles-dir .
```

`dbt build` runs models, seeds, snapshots, and the full test suite against the
local DuckDB file. Neither the warehouse file nor the raw extraction output is
committed.

### Extraction options

```bash
python -m extraction.pull_matches --help

  --riot-id NAME#TAG   Riot ID to pull (defaults to RIOT_ID in .env)
  --count N            Number of matches to fetch (default 20)
  --queue ID           Restrict to a queue, e.g. 420 for ranked solo/duo
  --start-time TS      Only matches after this epoch second
  --output DIR         Where to land raw JSON (default RAW_DATA_DIR)
  --no-load            Land raw JSON but skip the DuckDB load
```

## Development

```bash
pytest                      # unit tests for the extraction layer
dbt build --profiles-dir .  # models, seeds, snapshots, and dbt tests
```

### CI

`.github/workflows/ci.yml` runs three jobs on every push:

1. **No committed secrets** — fails if `.env` is tracked or if anything that
   looks like a Riot API key made it into the tree.
2. **Python tests** — `pytest` over the extraction layer. The Riot client is
   tested against a fake session, so CI never touches the network.
3. **dbt build** — `ci/generate_fixtures.py` writes deterministic synthetic
   match data in the same shape extraction lands, then `dbt build` runs every
   model, snapshot, seed, and test against it.

CI never calls the Riot API: that would require a key in the repository and
would spend rate limit on every push.

### Refreshing static data

```bash
python -m extraction.fetch_static_data   # rewrites seeds/champion_static.csv
```

Data Dragon needs no API key. The seed is committed so `dbt build` works
offline, which is what lets CI run without credentials.

## License

MIT. See `LICENSE`.
