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
| [0011](0011-polymarket-api-shape-and-full-history-pricing.md) | Polymarket's real API shape, and getting full-history pricing past a 10,000-trade cap | Accepted |
| [0012](0012-cross-platform-canonical-trade-schema.md) | A canonical cross-platform trade schema, built and validated on a real 60-market sample | Accepted |
| [0013](0013-platform-calibration-comparison-as-a-deliberate-ds-exception.md) | Real-money vs. play-money calibration comparison, a deliberate exception to keeping this project DE-scoped | Accepted |
| [0014](0014-semantic-candidate-matching-local-rag.md) | Semantic cross-platform market matching: local embeddings + local LLM (RAG), not an API | Accepted |
| [0015](0015-databricks-asset-bundles-jobs-not-all-purpose.md) | Databricks Asset Bundles + Jobs, not all-purpose compute or click-built resources | Accepted |
| [0016](0016-delta-live-tables-vs-plain-notebooks.md) | Delta Live Tables (SQL), not plain PySpark/SQL notebooks, replacing dbt | Accepted |
| [0017](0017-unity-catalog-schema-design.md) | Unity Catalog schema design: one catalog, dbt-layer-mirroring schemas | Accepted |
| [0018](0018-unity-catalog-volumes-not-dbfs.md) | Unity Catalog Volumes, not DBFS, for landed raw data | Accepted |
| [0019](0019-serverless-compute.md) | Serverless compute, not classic clusters, for both the ingestion Job and the DLT pipeline | Accepted |
| [0020](0020-rag-matching-stays-local.md) | Cross-platform market matching (RAG) stays local, not ported to Databricks | Accepted |
