# Architecture Decision Records

Short, dated records of the non-obvious calls made on this project and why. Not the *what* (the code shows that), the *why*, including what was given up. New ones get added as decisions get made, not written retroactively to look tidy.

| ADR | Decision | Status |
|---|---|---|
| [0001](0001-data-source-manifold-not-kalshi.md) | Data source: Manifold Markets, not Kalshi | Accepted |
| [0002](0002-spark-despite-small-data-volume.md) | Use Spark despite data that would fit in pandas | Accepted |
| [0003](0003-kubernetes-job-not-cronjob-or-deployment.md) | Kubernetes Job, not CronJob or Deployment | Accepted |
| [0004](0004-local-warehouse-duckdb-then-postgres.md) | Local warehouse: DuckDB first, Postgres-as-StatefulSet as phase 2 | Accepted |
| [0005](0005-elt-not-etl-transformation-lives-in-dbt.md) | ELT, not ETL: transformation lives in dbt, not Spark | Accepted |
| [0006](0006-raw-layer-jsonl-immutable.md) | Raw layer: JSON Lines, immutable, full API payloads (not CSV) | Accepted |
| [0007](0007-search-limit-truncation.md) | Small `limit` values silently truncate `/v0/search-markets` results | Accepted |
| [0008](0008-kickoff-time-enrichment-openfootball.md) | Kickoff-time enrichment from openfootball, seeded and matched by strict pattern | Accepted |
| [0009](0009-stretch-marts-match-price-history-and-outright-odds.md) | Stretch marts: match price history, outright odds scoped to one market out of ~15 near-duplicates | Accepted |
| [0010](0010-polymarket-eligible-as-a-future-data-source.md) | Polymarket verified as an eligible future data source, not yet integrated | Accepted |
