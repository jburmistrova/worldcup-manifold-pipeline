-- Unity Catalog structure for the Databricks port. Idempotent (IF NOT EXISTS
-- throughout), documents what Phase 0 verified interactively via the SQL
-- Statement Execution API against the Free Edition serverless warehouse
-- (raw `databricks catalogs create` failed here: Free Edition's default
-- storage isn't wired up for the plain REST call, only for SQL-driven
-- creation or the UI -- see ADR-0018).
--
-- Schema names mirror dbt's staging/intermediate/marts layers 1:1 (see
-- dbt/dbt_project.yml), so the two pipelines stay legible side by side, not
-- because Unity Catalog requires this shape.

CREATE CATALOG IF NOT EXISTS worldcup_manifold
  COMMENT 'World Cup 2026 prediction-market pipeline, Databricks port of the local Spark+dbt project';

CREATE SCHEMA IF NOT EXISTS worldcup_manifold.raw
  COMMENT 'Landed raw JSON (Unity Catalog Volume) + bronze Delta, mirrors data/raw/ and data/processed/';

CREATE SCHEMA IF NOT EXISTS worldcup_manifold.staging
  COMMENT 'Mirrors dbt models/staging: pure rename/type per platform, no business logic';

CREATE SCHEMA IF NOT EXISTS worldcup_manifold.intermediate
  COMMENT 'Mirrors dbt models/intermediate: cross-platform reconstruction (VWAP, repricing, kickoff matching)';

CREATE SCHEMA IF NOT EXISTS worldcup_manifold.marts
  COMMENT 'Mirrors dbt models/marts: the calibration/efficiency/outright-odds marts';

-- Landed-JSON volume: what ingest/*.py's local data/raw/*.jsonl becomes on
-- Databricks. Managed (not external): Free Edition has no external storage
-- credential to point at, and nothing here needs one.
CREATE VOLUME IF NOT EXISTS worldcup_manifold.raw.landed_json
  COMMENT 'Raw API payloads (Manifold + Polymarket), mirrors data/raw/*.jsonl';
