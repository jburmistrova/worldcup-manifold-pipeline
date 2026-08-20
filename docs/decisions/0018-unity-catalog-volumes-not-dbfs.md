# ADR-0018: Unity Catalog Volumes, not DBFS, for landed raw data

**Status:** Accepted
**Date:** 2026-08-19

## Context

The local pipeline's ingestion scripts write raw JSON Lines to local disk (`data/raw/`). Something has to play that role on Databricks: somewhere the ingestion notebooks land raw API payloads before the Spark flatten step reads them. Databricks historically offered two answers here -- DBFS (Databricks File System, a workspace-wide, largely ungoverned storage layer) and, more recently, Unity Catalog Volumes (governed, catalog/schema-scoped file storage with the same access-control model as tables). Worth checking which one this workspace actually offers before writing ingestion code against either, not assumed from general Databricks knowledge that may be stale.

## What Phase 0 found, empirically

`databricks fs ls dbfs:/` on this Free Edition workspace returned exactly three entries: `Volumes`, `Workspace`, `databricks-datasets`. No writable legacy DBFS root folder (no `FileStore`, no arbitrary top-level path) -- Volumes is not just the recommended path here, it's the only one this workspace actually exposes for something like this project's raw JSON. Confirmed with a real write/read/delete round-trip against a UC Volume (`worldcup_manifold.raw.landed_json`) before writing a single line of ingestion code, not assumed to work from the fact that the path existed.

## Decision

**Unity Catalog Volume (`worldcup_manifold.raw.landed_json`), created via `CREATE VOLUME` (see `databricks/uc_setup/create_catalog_schema.sql`), is where every ingestion notebook lands raw JSON, and where the two static dbt seeds (`team_aliases.csv`, `worldcup_schedule.csv`) were copied for the DLT staging layer to read.** Governed under the same catalog/schema grant model as everything else in this pipeline (ADR-0017), not a separate, ungoverned storage area a table's own access controls don't reach.

## Consequences

**Gained:** raw landed data that's subject to the same Unity Catalog grants (ADR-0017's `grants.sql`) as the tables built from it, and a decision that didn't need to be argued from first principles -- the workspace's own storage layout already answered it.

**Not applicable here:** the classic DBFS-vs-Volumes tradeoff discussion (Volumes being newer/slower to adopt, DBFS being simpler for quick scripts) doesn't really apply on this specific workspace, since DBFS root isn't meaningfully available to write into in the first place. Worth naming plainly: this wasn't a close call decided on governance merits, it's what Free Edition actually offers.
