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
