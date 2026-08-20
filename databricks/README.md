# Databricks path

A parallel, additive port of the pipeline in the repo root onto Databricks: PySpark ingestion as a Databricks Job, Delta Live Tables (Spark Declarative Pipelines) replacing dbt's staging/intermediate/marts layers, and Unity Catalog governance -- built to gain real, verifiable Databricks experience, not to replace the original local Spark+dbt build documented in the rest of this repo. See the root [README](../README.md) and [PROJECT_SPEC.md](../PROJECT_SPEC.md) for that original build; nothing here edits or removes it.

Runs on **Databricks Free Edition** (the tier with Unity Catalog and DLT/Spark Declarative Pipelines included, not the older Community Edition, which has neither -- confirmed before building anything here, see [ADR-0015](../docs/decisions/0015-databricks-asset-bundles-jobs-not-all-purpose.md)).

## What's here

```
databricks/
  databricks.yml                # Declarative Automation Bundle (DAB) root config
  resources/
    ingest_job.job.yml          # Task 1: ingestion + flatten, as a Databricks Job
    dlt_pipeline.pipeline.yml   # Task 2: the DLT/SDP pipeline
  src/
    notebooks/                  # ingest_manifold.py, ingest_polymarket.py, flatten_to_delta.py, retry_get.py
    pipelines/worldcup/transformations/
      staging/                  # 8 models, port of dbt/models/staging
      intermediate/             # 5 models, port of dbt/models/intermediate
      marts/                    # 6 models, port of dbt/models/marts
  uc_setup/
    create_catalog_schema.sql   # catalog/schema/volume creation (idempotent)
    grants.sql                  # real, applied Unity Catalog grants
  evaluation/
    recompute_metrics.py        # re-verifies Brier score / liquidity tiers against the Databricks marts
  docs/
    unity_catalog.md            # catalog/schema structure, grants, lineage
    results-databricks.md       # actual numbers observed on Databricks, compared to the local pipeline's
  ci_lint.py                    # the CI lint this bundle actually gets (see below)
```

## How to run it

Needs a Databricks Free Edition workspace and the `databricks` CLI (`brew install databricks/tap/databricks`), with a profile configured (`~/.databrickscfg`, a personal access token scoped to at least `jobs`, `pipelines`, `unity-catalog`, `sql`, `clusters`, `workspace`, `files` -- not "All APIs", per Databricks' own recommendation).

```bash
# One-time: Unity Catalog structure (or apply via the SQL warehouse UI)
databricks bundle validate --profile <profile>
databricks bundle deploy -t dev --profile <profile>

# Task 1: ingestion + flatten (writes to a UC Volume + bronze Delta tables)
databricks bundle run worldcup_ingest_and_flatten -t dev --profile <profile>

# Task 2: DLT pipeline (staging -> intermediate -> marts)
databricks bundle run worldcup_dlt -t dev --profile <profile>
```

`uc_setup/create_catalog_schema.sql` and `uc_setup/grants.sql` are documentation of what was actually run against the SQL warehouse (via the Statement Execution API) to stand up `worldcup_manifold`'s catalog/schema/volume structure and grants before any of the above -- run them yourself against a SQL warehouse if starting from a clean workspace.

## Re-verifying the metrics

```bash
pip install requests
export DATABRICKS_WAREHOUSE_ID=<warehouse-id>   # from `databricks warehouses list`
python databricks/evaluation/recompute_metrics.py
```

(Uses the SQL Statement Execution REST API directly, not `databricks-sql-connector` -- that library's Thrift-based connect hung indefinitely in the environment this was built in; see the script's own docstring.)

See [docs/results-databricks.md](docs/results-databricks.md) for the actual numbers this produced, compared honestly against the original local-pipeline numbers in [docs/results.md](../docs/results.md).

## What's different from the local pipeline, and why

Every non-obvious call here has its own ADR, same convention as the original 14 -- these are new records (0015-0020), not edits to the original ones:

- [ADR-0015](../docs/decisions/0015-databricks-asset-bundles-jobs-not-all-purpose.md): Databricks Asset Bundles + Jobs, not all-purpose compute or click-built notebooks -- including two real bugs found only by actually running this on Databricks.
- [ADR-0016](../docs/decisions/0016-delta-live-tables-vs-plain-notebooks.md): DLT vs. plain PySpark/SQL notebooks, and the full dbt-test-to-DLT-expectation mapping, including where DLT can't express the same check.
- [ADR-0017](../docs/decisions/0017-unity-catalog-schema-design.md): the catalog/schema design.
- [ADR-0018](../docs/decisions/0018-unity-catalog-volumes-not-dbfs.md): Volumes, not DBFS -- and why that wasn't really a close call on this workspace.
- [ADR-0019](../docs/decisions/0019-serverless-compute.md): serverless vs. classic compute.
- [ADR-0020](../docs/decisions/0020-rag-matching-stays-local.md): why the cross-platform RAG matching step (sentence-transformers + local Ollama) stays local, not ported here -- checked empirically, not assumed.

## What this doesn't do

No live smoke test in CI (`.github/workflows/ci-databricks.yml` is lint-only -- see that file and `ci_lint.py`'s own docstring for exactly what it does and doesn't catch). No schedule/trigger on the ingestion Job (this is a one-time backfill, same framing as the original Kubernetes Job). The cross-platform RAG matching step is unchanged and stays local (ADR-0020).
