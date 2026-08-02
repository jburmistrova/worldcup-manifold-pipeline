# ADR-0004: Local warehouse, DuckDB first, Postgres-as-StatefulSet as phase 2

**Status:** Accepted
**Date:** 2026-07-30

## Context

dbt needs some database to run its models against. For a local, single-machine setup with no cloud warehouse account, the realistic options are:

- **DuckDB**: an embedded, file-based SQL engine with native dbt support (`dbt-duckdb`). Needs no separate service, container, or credentials. dbt just points at a file.
- **Postgres, run inside the cluster**: requires a `StatefulSet` (not a Deployment, replicas need stable identity and their own storage, not to be interchangeable) plus a `PersistentVolumeClaim` so data survives pod restarts, plus a `Service` to expose it to the dbt container, plus `Secret`-managed credentials.

The Job built for ADR-0003 is **stateless**. It runs, does its work, and Kubernetes doesn't need to remember anything about it afterward. That's one category of Kubernetes problem. A database is the opposite: it must survive restarts with its data intact, which is a materially different, commonly-interviewed Kubernetes concept (`PersistentVolumeClaim`, `StorageClass`, `StatefulSet`) that a stateless Job never touches. Running only DuckDB means zero exposure to that side of Kubernetes in this project.

## Decision

Get the full pipeline (ingest -> Spark -> dbt -> marts) working end-to-end against **DuckDB first**, as a real, working, demoable milestone. Then, as an explicit, separately-labeled second phase (not because the pipeline needs it), swap DuckDB for **Postgres running as a Kubernetes StatefulSet with a PVC**, specifically for the stateful-workload practice.

## Consequences

**Gained:** hands-on with a second, harder class of Kubernetes workload beyond the stateless Job. Genuinely different interview material.

**Caveat, same honesty pattern as ADR-0003:** on a single-node local cluster, the PVC is backed by a local `hostPath` volume, not real durable network-attached storage. This teaches the PVC/StatefulSet *API and mechanics* well, but doesn't demonstrate the full "survives even if the whole node dies" value a real multi-node cluster would.

**Risk being managed:** sequencing phase 2 after a working DuckDB baseline avoids a database-ops detour blocking a demoable pipeline. Formalized in `PROJECT_SPEC.md`'s "Scope: core vs. stretch." Phase 2 is explicitly stretch, not required for the project to count as done.

## Update (2026-08-02): built as a selectable target, not a swap

Reconsidered "swap" once it came time to actually build phase 2. A hard swap would mean CI and every local run permanently depend on a running Postgres service just to build the project at all, trading DuckDB's real advantage (zero dependencies, dbt just points at a file) for a hands-on demonstration that doesn't need to be the *only* path. Implemented instead as a second dbt target (`dbt build --target postgres`, see `dbt/profiles.yml`): `dev` (DuckDB) stays the default for everything, `postgres` is opt-in, pointed at either `k8s/postgres.yaml`'s StatefulSet (via `kubectl port-forward`) or a throwaway service container in CI. Same models, same tests, a different warehouse underneath, selected without touching the dbt project itself.

**Wiring the second target into CI surfaced real, previously-invisible DuckDB dependencies**, not just config work. Every one of these built and passed silently under DuckDB alone, because nothing had ever pointed different SQL at them before:

- **DuckDB reads Parquet directly** (`external_location` in `_sources.yml`); Postgres has no equivalent. Added `spark/load_parquet_to_postgres.py`, a real load step DuckDB never needed. Its first version used pandas' row-by-row `to_sql()`, fine for thousands of rows, genuinely too slow for the full 1.17M-row `bets` table (multiple minutes). Rewrote to create the table via `to_sql()` (0 rows, schema only) then bulk-load with Postgres' own `COPY`: 17 seconds for the same data.
- **Postgres folds every unquoted identifier to lowercase**; DuckDB doesn't. The loader was creating genuinely mixed-case columns (`contractId`) that dbt's already-unquoted SQL references (also `contractId`, folded to `contractid` by Postgres at query time) could never match. Fixed by lowercasing DataFrame columns before load.
- **`epoch_ms()` and `try_cast()` are DuckDB-specific functions.** Even dbt-core's own cross-database `safe_cast` macro admits most databases don't support a true try-cast and falls back to a plain `cast`. Wrote two small adapter-dispatched macros (`dbt/macros/epoch_ms_to_timestamp.sql`, `dbt/macros/try_cast_timestamp.sql`) instead of forking the SQL per adapter by hand.
- **`double` isn't a valid Postgres type name** (`double precision` is), which broke every mart with an enforced contract, since dbt casts to the literal `data_type` string from the yml. Switched every `data_type: double` to `data_type: double precision`, which DuckDB also accepts as a standard alias, one name working on both adapters instead of an adapter-conditional.
- **Nullable boolean columns silently degrade.** `isFilled`/`isCancelled` have real nulls; a native array can't hold both booleans and nulls, so pandas falls back to generic `object` dtype, indistinguishable from a string column by dtype alone. `to_sql()` then guessed `TEXT`. Fixed by reading each column's true type from Parquet's own schema (via `pyarrow`) and forcing an explicit `Boolean` type override for exactly those columns, rather than trusting pandas' inference.

**Deliberately not made portable: ADR-0008/0009's kickoff-time matching chain** (`int_market_kickoff_times` and everything downstream: `int_answer_kickoff_times`, `int_pre_kickoff_probability`, `mart_pre_kickoff_calibration`, `mart_match_price_history`). It depends on DuckDB's RE2-based `regexp_extract`/`regexp_matches`, and Postgres' own regex functions have different signatures (`regexp_match` returns an array, not a matched group directly). Disabled on the postgres target with `{{ config(enabled = target.type != 'postgres') }}`, one line per model, rather than rewritten. Full cross-database regex portability isn't what this phase exists to demonstrate; the point is the StatefulSet, and `mart_market_efficiency`, `mart_trade_calibration`, and `mart_outright_odds_over_time`, the marts that don't touch that chain, are fully portable and verified identical on both adapters (same row counts, same test results, run against both the small CI fixture and the full real dataset before this was called done).

CI now runs both: the existing DuckDB build, then a second job step that loads a Postgres service container from the same Parquet output and runs `dbt build --target postgres` against it, so this target is exercised on every push, not just the one time it was built.
