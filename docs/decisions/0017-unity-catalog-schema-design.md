# ADR-0017: Unity Catalog schema design -- one catalog, dbt-layer-mirroring schemas

**Status:** Accepted
**Date:** 2026-08-19

## Context

Unity Catalog needs a real catalog/schema structure before anything can be registered under it -- this is the governance piece the migration's target job descriptions specifically ask about (see the migration's own framing), so it needed a deliberate structure, not whatever fell out of running `CREATE TABLE` statements in the default `workspace` catalog Free Edition ships with.

## Decision

**One catalog, `worldcup_manifold`**, not one catalog per layer or per platform. This project is one bounded dataset (a single tournament, two platforms, already namespaced by table/column names like `polymarket_*`), not a multi-tenant or multi-team workspace where separate catalogs would earn their keep as an isolation boundary. A second catalog here would be governance theater, not real isolation of anything.

**Four schemas, mirroring the dbt project's own layer names exactly: `raw`, `staging`, `intermediate`, `marts`.** Verified real and intentional, not incidental: `dbt/dbt_project.yml` already names these layers `staging`/`intermediate`/`marts`; `raw` is new here since dbt's local pipeline uses a filesystem directory (`data/raw/`) and a DuckDB `external_location`, not a schema, for that layer. Keeping the same three post-raw names means someone who knows the dbt project already knows this one's shape -- a deliberate legibility choice, not a technical requirement Unity Catalog imposes.

**`raw` holds both the landed-JSON Volume (`worldcup_manifold.raw.landed_json`, ADR-0018) and the bronze Delta tables `flatten_to_delta.py` writes** (`markets`, `market_answers`, `bets`, `polymarket_markets`, `polymarket_trades`, `polymarket_prices`) -- one schema for "not yet transformed," not a separate `bronze` schema. The dbt original doesn't distinguish "raw files" from "flattened Parquet" as two different governed locations either (both are just `data/raw/` and `data/processed/` on disk, outside any schema); `raw` here plays both those roles for the same reason: neither one is meant to be queried directly by anyone downstream of the pipeline itself.

**Grants scoped by layer, not by table (`databricks/uc_setup/grants.sql`, real and applied, verified via `SHOW GRANTS`, not just SQL that was written but never run):** `USE CATALOG` + `USE SCHEMA` + `SELECT` on `marts` for `account users`; `USE SCHEMA` only (no `SELECT`) on `raw`/`staging`/`intermediate`. Marts are the real query surface, the same boundary a production warehouse would enforce between "the layer analysts query" and "the layers that exist to be read by the pipeline itself." This is a single-user Free Edition workspace, so there's no second person this actually restricts today -- the point of applying it for real (not just writing the SQL) is demonstrating the mechanic, the same "practice the muscle on a workload too small to require it" framing ADR-0002 already gives Spark.

## Consequences

**Gained:** a catalog structure that's legible against the existing dbt project without a lookup table, real applied grants (verified via `SHOW GRANTS ON SCHEMA worldcup_manifold.marts`, not just SQL that was written but never run), and a genuine layer boundary between "pipeline-internal" and "query surface."

**Cost:** the `raw` schema conflates two genuinely different things (immutable landed JSON, mutable/overwritten bronze Delta) that a stricter medallion design would separate into `raw`/`bronze`. Kept together deliberately, matching the dbt original's own two-different-filesystem-locations-no-schema-boundary precedent, not a schema Unity Catalog forced this shape on.

**Not done:** row-level security or column masks (ADR mentions these exist in Unity Catalog's Public Preview feature set) -- nothing in this dataset needs them; a real feature this workload doesn't require, not a gap.
