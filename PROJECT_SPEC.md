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
- ~~The full favorite-longshot-bias-by-liquidity breakdown, beyond the base calibration comparison~~ — done 2026-07-31, see below

## Target outcome

Resume bullet: *"Built a Spark + dbt pipeline over a public prediction-market API, reconstructing implied-probability history for 2026 World Cup markets and measuring market calibration against actual outcomes, deployed as a Kubernetes batch job."*

This should be true, specific, and something I can defend line by line in an interview — not just something that exists in a repo. That includes being able to explain the data-source ToS check itself if asked (see pivot note above).

## Status

Done (2026-07-30): data source confirmed; full ingestion working (`ingest/pull_markets.py`, `pull_market_answers.py`, `pull_bets.py`) writing raw JSON Lines (not CSV — see [ADR-0006](docs/decisions/0006-raw-layer-jsonl-immutable.md) for why); Spark extract+load step working (`spark/flatten_to_parquet.py`), producing typed Parquet for all three datasets; environment upgraded to current, non-EOL Python/Java (`requirements.md`); problem statement and architecture written up; 6 ADRs logged; README and best-practices checklist maintained throughout.

Along the way: found and fixed a real pagination-instability bug (duplicate markets), a real mistake in how it was first fixed (mutated raw data in place — corrected), two real CSV-parsing bugs that motivated switching the raw format to JSON entirely, and — while building `int_market_implied_probability` — a missing field (`answerId`, required to keep multi-choice markets' per-answer probability tracks separate) and a third real-trade filtering case (zero-amount seeding events breaking a VWAP calculation with `0/0`). All documented rather than quietly cleaned up — see `docs/data_dictionary.md`'s History section and ADR-0006.

Done (2026-07-31): `dbt/` project set up against DuckDB — full staging layer (`stg_manifold_markets`, `stg_manifold_market_answers`, `stg_manifold_bets`) and `int_market_implied_probability` (running VWAP + repricing-jump ranking, correctly partitioned per market/answer), 20 passing tests.

A fourth real bug found and fixed the same day, bigger than the earlier ones: a small `limit` value was silently truncating `/v0/search-markets` results — 232 of 621 real markets (37%) were missing from the entire dataset, with zero errors and zero variance across repeated runs, so nothing about it looked broken (see [ADR-0007](docs/decisions/0007-search-limit-truncation.md)). Fixed and re-ingested everything: 621 markets (was 389), 4,545 answers (was 3,286), 1,176,547 raw bets (was 400,207), 212,749 real trades after filtering (was 133,125). Also added retry-with-backoff to `pull_bets.py` after a real transient 503 crashed a run partway through.

Done: `mart_market_efficiency` — unions resolved `BINARY` markets and `MULTIPLE_CHOICE` answers into one shape, bucketed by decile. Real result: a textbook favorite-longshot bias pattern (longshots overpriced, favorites slightly underpriced, most pronounced and best-sampled at the extremes). Full writeup with a chart in `docs/results.md`, chart reproducible via `analysis/plot_calibration.py`. This is the actual core-scope deliverable — the pipeline now answers both problem-statement questions, not just moves data around.

Done (2026-07-31): closed both remaining gaps in the analysis. (1) The original Brier-score-vs-Manifold comparison (0.0185) turned out to be measuring something different from Manifold's own number — theirs is trade-weighted across a market's lifetime, ours was one resolution-time snapshot per prediction. Built `mart_trade_calibration` to replicate Manifold's exact stated methodology (trades on `BINARY` markets with 15+ traders, predicted probability = average of before/after each trade) — the matched comparison is 0.1305 vs. Manifold's 0.1748, a believable gap instead of a suspicious one. Documented as a generalizable lesson in `lessons_learned.md`. (2) Built the liquidity-vs-calibration breakdown (previously listed as stretch, above) — raw numbers looked like low liquidity predicts better calibration, but that was the same easy-bucket confound as the Brier comparison; controlling for it, the three liquidity tiers land in the same noisy range with no credible relationship, though sample sizes (n≈30) are too thin for a confident null. Full writeup in `docs/results.md`, reproducible via `analysis/compute_calibration_metrics.py`.

Done (2026-07-31): Kubernetes containerization built and verified, though not yet deployed to the actual cluster. `Dockerfile` (`eclipse-temurin:25-jre` base — already has Java 25's `JAVA_HOME` set correctly, and its Ubuntu 26.04 apt repo happens to package exactly Python 3.14, so both runtimes install from one distro's package manager instead of copying binaries across two differently-based images), `run_pipeline.sh` entrypoint running the same steps as README's "How to run it," `k8s/job.yaml` (a Job, not CronJob/Deployment, per ADR-0003), `k8s/configmap.yaml` (externalizes `SEARCH_TERM`/`PAGE_LIMIT`/`MAX_RETRIES`, previously hardcoded Python constants). Docker Desktop and minikube installed along the way — real setup bug found and fixed: two parallel Homebrew installs (Intel at `/usr/local`, native arm64 at `/opt/homebrew`) meant `brew install --cask docker` silently fetched the wrong architecture build (full story in `requirements.md`). Also found and fixed, via containerizing on a genuinely fresh filesystem: none of the three ingest scripts (nor `plot_calibration.py`) ever created their own output directories, only working locally because those directories already existed from early manual setup; and a real Manifold API read-timeout under rapid repeated calls, confirmed (not assumed) to be genuine API slowness rather than a Docker networking artifact by reproducing the same response times from the host directly — both documented in `lessons_learned.md` and `docs/data_engineering_best_practices.md`. Full pipeline verified end-to-end inside the container via `docker run` (all 1.17M+ bets, all dbt tests passing) before ever touching `kubectl`.

Done (2026-07-31): closed the gap between "this pipeline runs" and "this looks like real production dbt/DE practice," not because the dataset needed any of this, but because none of it had been exercised yet. `stg_manifold_bets` is now a genuine incremental model (`unique_key='bet_id'`, filtered on `created_at`) — proven both directions, not just configured: a no-op rerun with no new data adds zero rows, and a synthetic late-arriving bet, added directly to the source Parquet, comes through as exactly one new row with no duplication. Added `dbt_utils` as a real third-party package (`dbt/packages.yml`), with a genuine `unique_combination_of_columns` test on `(market_id, answer_id)` — the actual uniqueness guarantee on `mart_market_efficiency`, since neither column is unique alone. Both marts now have `contract: {enforced: true}` with explicit column types — verified for real by deliberately breaking a declared type and confirming `dbt build` refused to run, not just trusting the YAML. Extracted the decile-bucketing formula, previously copy-pasted between both marts, into a shared macro (`dbt/macros/prob_bucket.sql`). `dbt docs generate`/`serve` confirmed working. CI (`.github/workflows/ci.yml`) runs the real pipeline (Spark + full `dbt build`, all tests) on every push, against a small committed fixture (`tests/fixtures/raw/` — 5 real markets) rather than the live, rate-limited Manifold API. Along the way, caught `dbt/package-lock.yml` wrongly gitignored (it's a lockfile meant to be committed, like `poetry.lock`, unlike `dbt_packages/` itself) and several stale rows in `docs/data_engineering_best_practices.md` describing an earlier, already-superseded state of the project.

## Remaining for core scope

The actual `kubectl apply` deployment to a running minikube cluster — everything up to that point (image, manifests, end-to-end container verification) is done. See "Scope: core vs. stretch" above for the rest of core scope, which is otherwise complete.
