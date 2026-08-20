# World Cup 2026 Prediction-Market Pipeline

A Spark + dbt pipeline over Manifold Markets' public API, reconstructing implied-probability history for 2026 World Cup markets and testing whether known prediction-market biases (calibration drift, the favorite-longshot bias) hold in a narrower, faster-moving, more correlated domain than the politics/macro markets most existing research covers. Deployed as a Kubernetes batch job.

Extended with a second data source, Polymarket, a real-money exchange, to answer a different question: does calibration actually differ between a real-money market and Manifold's own Mana, given Mana can be bought with cash but never converted back? See [docs/results.md](docs/results.md)'s addendum for the answer, and [ADR-0010](docs/decisions/0010-polymarket-eligible-as-a-future-data-source.md) through [ADR-0013](docs/decisions/0013-platform-calibration-comparison-as-a-deliberate-ds-exception.md) for how it was built.

Extended again with a real, local RAG pipeline (embeddings + a local LLM, no API key anywhere in this project) to find cross-platform market pairs beyond the one hand-picked outright-winner pair the marts above use. Evaluated honestly against real ground truth, not just demoed: retrieval alone hits 100%, adding an LLM reasoning layer on top drops that to 58%, a real, measured, and specifically diagnosed regression, not a number tuned until it looked good. See [docs/results.md](docs/results.md)'s addendum and [ADR-0014](docs/decisions/0014-semantic-candidate-matching-local-rag.md) for the full build and the honest result.

Ported onto Databricks as a second, parallel path: PySpark ingestion as a Databricks Job, Delta Live Tables replacing dbt, Unity Catalog governance. Additive, not a rewrite -- everything above still runs exactly as documented, nothing was edited or removed. See [Databricks path](#databricks-path) below.

Built to gain real, hands-on experience with Spark, dbt, Kubernetes, and Postgres-as-a-StatefulSet. Tools I hadn't used in production before this project. See [Architecture Decision Records](docs/decisions/) for the reasoning behind every non-obvious choice, including the ones that add complexity this specific workload didn't strictly need.

**A note on how this was built:** my background is in data engineering. I used Claude Code throughout this project, for pairing on the code and for help with the analysis and understanding it. That means there could be errors I didn't catch. Verify anything here you're relying on, don't take it on faith.

**Status (2026-08-08):** core scope complete, plus two further extensions beyond it. Ingestion (621 Manifold markets, 4,545 answers, 1.18M bet records; 6,358 Polymarket markets, 4.4M trades, 3.2M price points), Spark, dbt's full staging/intermediate/marts layers across both platforms, a real Kubernetes Job deployment (verified end to end on minikube), a selectable Postgres target (StatefulSet), CI exercising the gated Polymarket path on every push, a real RAG pipeline for cross-platform market matching, and the results writeup are all built and verified. See [docs/results.md](docs/results.md) for the actual findings, including both cross-platform comparisons. See `PROJECT_SPEC.md` for the full, dated history; everything logged there as "Done" is done.

## Problem statement

Manifold's own platform-wide calibration is well-documented. But there's no public breakdown by category, and none for a single-elimination sports tournament specifically. Two concrete questions:

1. **Calibration comparison.** Does calibration at the World Cup 2026 level match Manifold's platform-wide numbers, or does this narrower, more correlated, faster-moving domain behave differently?
2. **Favorite-longshot bias.** The most consistently replicated finding in prediction-market research generally: markets overprice unlikely outcomes, underprice likely ones. Does it show up here? And does market liquidity actually predict better calibration, or does that relationship hold up as poorly as some existing research suggests?

Full discussion in [docs/architecture.md](docs/architecture.md). **Answers, with a chart: [docs/results.md](docs/results.md).**

## Architecture

```mermaid
flowchart LR
    A[Manifold API] -->|raw JSON| B[Ingest, Python]
    A2[Polymarket API<br/>Gamma / Data / CLOB] -->|raw JSON| B2[Ingest, Python]
    B --> C[Spark: parse + flatten,<br/>no business logic]
    B2 --> C2[Spark: parse + flatten,<br/>no business logic]
    C -->|Parquet| D[(DuckDB, default;<br/>Postgres StatefulSet, selectable)]
    C2 -->|Parquet| D
    D --> E[dbt staging: per-platform,<br/>pure rename/type]
    E --> F[int_all_market_ticks:<br/>canonical cross-platform schema]
    F --> G[int_market_implied_probability<br/>VWAP, repricing detection]
    G --> H[mart_market_efficiency]
    G --> I[mart_outright_odds_over_time]
    G --> J[mart_platform_calibration_comparison]

    subgraph K8s Job
    B
    C
    E
    end
```

## What I'd do differently in production

This project intentionally uses more infrastructure than the workload strictly needs, to practice it. Short version: no Airflow (ingest/Spark/dbt run as one Kubernetes Job instead of a DAG), this is a one-time batch backfill rather than a live Kafka+Streaming pipeline, and the whole thing runs at a scale (~1.2M raw rows, one laptop) where none of Spark or Kubernetes' real value (distributed compute, multi-node scheduling, cluster-wide resource sharing) actually applies. Full dimension-by-dimension breakdown, including exactly which forcing functions would have to be true for each tool to earn its place for real: [docs/project_scale_vs_production.md](docs/project_scale_vs_production.md).

## How to run it

Locally, directly on your machine:

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # see requirements.md for JAVA_HOME setup

python ingest/pull_markets.py
python ingest/pull_market_answers.py
python ingest/pull_bets.py          # takes 10-15 minutes (~1.2M bet records)

python spark/flatten_to_parquet.py  # raw JSON -> typed Parquet

cd dbt
dbt deps                            # installs dbt_utils (see dbt/packages.yml)
dbt build --profiles-dir .          # builds + tests staging, intermediate, and marts

cd .. && python analysis/plot_calibration.py           # regenerates docs/images/calibration_chart.png
python analysis/compute_calibration_metrics.py         # Brier score + liquidity-tier numbers behind docs/results.md
```

Polymarket is a separate, optional addition, not part of the core pipeline above: `dbt build` never requires it, gated behind `INCLUDE_POLYMARKET` (default off, see `int_all_market_ticks.sql`). Run it to reproduce the cross-platform comparison in `docs/results.md`'s addendum:

```bash
python ingest/pull_polymarket_markets.py
python ingest/pull_polymarket_trades.py   # ~20-30 min at full scale (6,358 markets)
python ingest/pull_polymarket_prices.py   # ~30-60 min at full scale, chunked per market (ADR-0011)

python spark/flatten_polymarket.py

cd dbt && INCLUDE_POLYMARKET=true dbt build --profiles-dir .
cd .. && python analysis/compare_platform_calibration.py    # the significance test, ADR-0013
python analysis/compare_platform_predictions.py             # the descriptive team-by-team comparison
```

Semantic cross-platform market matching (ADR-0014) is a further, separate optional layer on top of Polymarket above: a local embeddings + local LLM (RAG) pipeline that finds candidate market pairs between the two platforms beyond the one hand-picked outright-winner pair the marts above use. Needs its own venv, built from the native arm64 Python (this project's main `venv/` is built from an Intel Homebrew path that can't install `torch`, see `requirements.md`), and a local [Ollama](https://ollama.com) install for the generation half, no API key involved:

```bash
/opt/homebrew/opt/python@3.14/bin/python3.14 -m venv venv-semantic-matching
source venv-semantic-matching/bin/activate
pip install -r requirements.txt -r requirements-semantic-matching.txt

brew install ollama
ollama serve &
ollama pull qwen2.5:7b   # ~4.7GB, one-time

python analysis/find_candidate_market_matches.py    # retrieval only, full corpus, ~5-10 min including one-time embedding
python analysis/explain_top_candidate_matches.py    # generation over the top 100 highest-confidence pairs, ~20 min
python analysis/evaluate_candidate_matches.py        # both halves scored against real ground truth, ~15 min
```

Or as a Kubernetes Job, on a local cluster (minikube, tested; kind should work identically):

```bash
docker build -t worldcup-pipeline:latest .
minikube start --driver=docker
minikube image load worldcup-pipeline:latest   # no registry involved, see k8s/job.yaml

kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/job.yaml
kubectl logs -f -l job-name=worldcup-pipeline   # watch it run
kubectl get jobs                                # STATUS: Complete when done, ~25-30 min
```

Both run the identical pipeline (same `run_pipeline.sh` entrypoint); the Kubernetes path just runs it inside a pod instead of your shell. See [ADR-0003](docs/decisions/0003-kubernetes-job-not-cronjob-or-deployment.md) for why this is a Job, not a Deployment or CronJob.

Postgres is also available as a selectable dbt target, DuckDB stays the default everywhere else, for the Kubernetes StatefulSet/PVC pattern specifically (see [ADR-0004](docs/decisions/0004-local-warehouse-duckdb-then-postgres.md)):

```bash
kubectl create secret generic postgres-credentials \
  --from-literal=POSTGRES_USER=worldcup \
  --from-literal=POSTGRES_PASSWORD=<your own value> \
  --from-literal=POSTGRES_DB=worldcup
kubectl apply -f k8s/postgres.yaml
kubectl port-forward svc/postgres 5432:5432 &

export POSTGRES_HOST=localhost POSTGRES_USER=worldcup POSTGRES_PASSWORD=<same value> POSTGRES_DB=worldcup
python spark/load_parquet_to_postgres.py        # Postgres has no DuckDB-style direct Parquet read, needs real tables loaded first
cd dbt && dbt build --profiles-dir . --target postgres
```

## Databricks path

A parallel, additive port onto Databricks (Free Edition), built to gain real, hands-on Databricks/PySpark/Delta Live Tables/Unity Catalog experience -- not a replacement for the local Spark+dbt build above, which stays exactly as documented. Same ingestion logic (offset pagination, retry/backoff), the same 19 dbt models faithfully re-implemented as Delta Live Tables (dbt tests mapped to DLT expectations, with every case DLT can't express the same check written up honestly), and real Unity Catalog governance (catalog/schema structure, applied grants, lineage). The cross-platform RAG matching step above stays local rather than moving here: a Databricks Free Edition notebook genuinely can't reach a model server on this laptop, confirmed empirically rather than assumed (see [ADR-0020](docs/decisions/0020-rag-matching-stays-local.md)).

```bash
databricks bundle deploy -t dev --profile <profile>
databricks bundle run worldcup_ingest_and_flatten -t dev --profile <profile>
databricks bundle run worldcup_dlt -t dev --profile <profile>
```

Every number in [databricks/docs/results-databricks.md](databricks/docs/results-databricks.md) was actually recomputed against the Databricks-produced marts after this migration, not carried over from the numbers above. Full instructions, architecture, and the six new Databricks-specific ADRs (0015-0020, additions alongside the original 14, not edits to them): [databricks/README.md](databricks/README.md).

## Browsing the data

To browse the data directly: `duckdb -ui manifold.duckdb` (from inside `dbt/`) opens DuckDB's built-in local web UI, a schema browser and SQL editor against the same database file dbt just built into. See [requirements.md](requirements.md) for the CLI install.

To browse the project's structure instead of the data (model lineage graph, column-level descriptions, which models depend on which): `dbt docs generate --profiles-dir . && dbt docs serve` (from inside `dbt/`) builds and serves dbt's own documentation site from the `description:` fields already written in each model's `schema.yml`.

## Data sources

- [Manifold Markets](https://manifold.markets) public API, no authentication required. See [ADR-0001](docs/decisions/0001-data-source-manifold-not-kalshi.md) for why this project doesn't use Kalshi despite starting there.
- [Polymarket](https://polymarket.com) public API (Gamma, Data, CLOB), also no authentication required for the read-only endpoints this project uses. Optional, see "How to run it" above. See [ADR-0010](docs/decisions/0010-polymarket-eligible-as-a-future-data-source.md) for the terms-of-use verification (read directly from the actual PDF, not a summary) and [ADR-0011](docs/decisions/0011-polymarket-api-shape-and-full-history-pricing.md) for the real API shape and its quirks.

See [docs/data_dictionary.md](docs/data_dictionary.md) for the schema of everything ingested from both.

## Project docs

- [docs/architecture.md](docs/architecture.md): problem statement, architecture, tool-by-tool reasoning
- [docs/results.md](docs/results.md): the actual finding, with a chart showing a real favorite-longshot bias pattern, honestly caveated
- [docs/data_dictionary.md](docs/data_dictionary.md): schema of ingested data
- [docs/decisions/](docs/decisions/): ADRs for every non-obvious call made on this project
- [docs/data_engineering_best_practices.md](docs/data_engineering_best_practices.md): checklist of standard DE practices, applied, planned, or deliberately skipped, and why
- [docs/project_scale_vs_production.md](docs/project_scale_vs_production.md): dimension by dimension, this project's actual scale vs. what would earn each tool's place at a real company
- [requirements.md](requirements.md): system prerequisites (Python, Java) and how to set them up, distinct from `requirements.txt`
- [ADR-0014](docs/decisions/0014-semantic-candidate-matching-local-rag.md): local embeddings + local LLM (RAG) cross-platform market matching
- [databricks/README.md](databricks/README.md): the Databricks port -- PySpark ingestion, Delta Live Tables, Unity Catalog, ADRs 0015-0020
