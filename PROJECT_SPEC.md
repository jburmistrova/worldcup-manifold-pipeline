# World Cup 2026 Prediction-Market Pipeline — Project Spec

**Data source pivot (2026-07-30):** Originally scoped around Kalshi. Kalshi's Developer Agreement (accepted when generating an API key) restricts API use to "facilitating a member's own trading" — collecting/storing data for analysis, and sharing it via a public GitHub repo, is explicitly out of scope without Kalshi's written authorization. The separate Data Terms of Use (covering the no-auth public endpoints too) is similarly restrictive. Switched to **Manifold Markets** instead: its Terms of Service explicitly permit building tools against the public API and using data for "academic research, personal projects, and non-commercial use" — only commercial resale or AI-model training requires a paid license. See `docs.manifold.markets/terms` and `docs.manifold.markets/data`.

## Why this project exists

Job evaluations run through career-ops (a separate project at `~/career/career-ops`) flagged the same recurring gaps across many applications: no hands-on Kubernetes, no production Spark experience, dbt as a certification only (not real project work). This project is designed to genuinely close those three gaps with one real, defensible portfolio piece — not to pad a resume with something I can't speak to in an interview.

**Ground rule for how I build this:** I'm using Claude Code as a pairing partner, not a ghost-writer. It should explain concepts as I go, generate boilerplate I then read and understand, and help me debug real errors rather than silently fixing them. The test at the end isn't "does it run" — it's "can I explain, in an interview, why the Kubernetes manifest is structured this way, what happens if a pod crashes, why I chose a Job over a CronJob, and what broke the first time I ran it."

## Data source

**Manifold Markets public API** — a play-money forecasting platform (not real financial stakes; trades happen in virtual "Mana"), used in academic prediction-market research. Public read endpoints need no auth: `/v0/search-markets`, `/v0/market/{id}`, `/v0/bets` for trade-level history. Docs: https://docs.manifold.markets/api

World Cup 2026 had real, meaningful engagement on Manifold: per-match markets, tournament-winner and Golden Boot-style prop markets, some individual markets with $1M+ in historical trading volume. The tournament already happened, so this is backfill/batch analysis over settled markets, same as originally planned.

**ToS check (done 2026-07-30):** confirmed via `docs.manifold.markets/terms` and `docs.manifold.markets/data` — personal, academic, and non-commercial use of API data (including posting the resulting code/analysis publicly) is explicitly permitted. Only commercial resale or AI/ML training requires a separate paid data license.

## Architecture

1. **Ingest** — pull every World Cup 2026-related market from Manifold's API, then full bet (trade) history for each. On Manifold, market probability is given directly (0-100%), unlike Kalshi where it's derived from contract price.

2. **Spark (PySpark)** — extract + load only: parse and flatten raw bet-tick JSON at scale (hundreds of markets × tick-level bets is real volume) into clean, partitioned Parquet. Deliberately no business logic here — see [ADR-0005](docs/decisions/0005-elt-not-etl-transformation-lives-in-dbt.md) for why the transformation work below moved to dbt instead of living here.

3. **dbt** — land Spark's flattened output, build `stg_manifold_bets` → `int_market_implied_probability` (probability-over-time reconstruction, volume-weighted average probability, repricing-jump detection — all as SQL) → marts:
   - `mart_match_price_history` — win-probability movement through each match
   - `mart_market_efficiency` — pre-kickoff implied probability vs. actual outcome, across all matches, to measure market calibration
   - `mart_outright_odds_over_time` — how the tournament-winner contract repriced match by match
   - dbt tests: prices bounded 0-100, no duplicate trade IDs, timestamps inside the tournament window

4. **Kubernetes** — containerize ingestion + Spark + dbt, deploy as a Kubernetes Job on a local cluster (minikube or kind). Framed honestly as a backfill/batch job (tournament's over, this isn't live-polling), but a real, working deployment.

## Scope: core vs. stretch

Called out explicitly (2026-07-30) after a documentation-heavy stretch got ahead of actual running code — a finished small thing beats an unfinished ambitious one, especially against real job-search timing.

**Core — what "done enough to show" means:**
- Ingest: markets, market answers (done), bets (next)
- Spark: parse/flatten bet JSON → Parquet, extract + load only
- dbt against DuckDB: `stg_manifold_bets` → `int_market_implied_probability` → **`mart_market_efficiency`** (the calibration mart — this one directly answers the problem statement's two questions, so it's the mart that has to exist) with dbt tests
- Kubernetes: containerized, running as a Job on minikube/kind
- A results writeup with at least one chart, as evidence the pipeline produces something real

**Stretch — valuable, but not required before calling this done:**
- `mart_match_price_history` and `mart_outright_odds_over_time` (the other two marts — nice additional demonstration, not load-bearing for the core question)
- Postgres-as-StatefulSet swap ([ADR-0004](docs/decisions/0004-local-warehouse-duckdb-then-postgres.md), phase 2)
- CI (GitHub Actions running dbt tests / unit tests)
- The full favorite-longshot-bias-by-liquidity breakdown, beyond the base calibration comparison

## Target outcome

Resume bullet: *"Built a Spark + dbt pipeline over a public prediction-market API, reconstructing implied-probability history for 2026 World Cup markets and measuring market calibration against actual outcomes, deployed as a Kubernetes batch job."*

This should be true, specific, and something I can defend line by line in an interview — not just something that exists in a repo. That includes being able to explain the data-source ToS check itself if asked (see pivot note above).

## Status

Done (2026-07-30): data source confirmed; full ingestion working (`ingest/pull_markets.py`, `pull_market_answers.py`, `pull_bets.py`) writing raw JSON Lines (not CSV — see [ADR-0006](docs/decisions/0006-raw-layer-jsonl-immutable.md) for why); Spark extract+load step working (`spark/flatten_to_parquet.py`), producing typed Parquet for all three datasets; environment upgraded to current, non-EOL Python/Java (`requirements.md`); problem statement and architecture written up; 6 ADRs logged; README and best-practices checklist maintained throughout.

Along the way: found and fixed a real pagination-instability bug (duplicate markets), a real mistake in how it was first fixed (mutated raw data in place — corrected), two real CSV-parsing bugs that motivated switching the raw format to JSON entirely, and — while building `int_market_implied_probability` — a missing field (`answerId`, required to keep multi-choice markets' per-answer probability tracks separate) and a third real-trade filtering case (zero-amount seeding events breaking a VWAP calculation with `0/0`). All documented rather than quietly cleaned up — see `docs/data_dictionary.md`'s History section and ADR-0006.

Done: `dbt/` project set up against DuckDB — full staging layer (`stg_manifold_markets`, `stg_manifold_market_answers`, `stg_manifold_bets`) and `int_market_implied_probability` (running VWAP + repricing-jump ranking, correctly partitioned per market/answer), 16 passing tests.

Next: `mart_market_efficiency` — core scope, the mart that actually answers the problem statement.

Next: `/v0/bets` ingestion (trade-level history — needed for probability-over-time, not just snapshots), then the Spark job against DuckDB. See "Scope: core vs. stretch" above for what's actually required to reach a demoable state.
