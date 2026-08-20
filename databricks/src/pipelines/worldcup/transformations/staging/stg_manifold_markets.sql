-- Port of dbt/models/staging/stg_manifold_markets.sql. Pure rename/type,
-- no business logic (ADR-0005). Reads the bronze Delta table flatten_to_delta.py
-- wrote, mirrors dbt's `source('manifold_raw', 'markets')`.
--
-- Materialized View, not Streaming Table: the bronze table is fully
-- overwritten by each ingestion run (a one-time tournament backfill, same
-- framing the original stg_manifold_bets.sql comment already gives), not a
-- genuinely incrementally-arriving file stream, so Auto Loader semantics
-- would misrepresent what's actually happening here. See ADR-0016.
--
-- dedup_ok: DLT expectations are row-level only, no native dataset-level
-- uniqueness check (unlike dbt's `unique` test). Ported via a COUNT(*)
-- OVER(...) window column turned into a row-level boolean -- kept visible
-- in the output, not hidden, a real and honest tradeoff vs. dbt's
-- test-only-no-schema-impact approach. See ADR-0016.
CREATE OR REFRESH MATERIALIZED VIEW stg_manifold_markets (
  CONSTRAINT market_id_not_null EXPECT (market_id IS NOT NULL) ON VIOLATION FAIL UPDATE,
  CONSTRAINT market_id_unique EXPECT (dedup_ok) ON VIOLATION FAIL UPDATE
)
AS
WITH base AS (
  SELECT
    id AS market_id,
    question,
    slug,
    url,
    outcomeType AS outcome_type,
    resolution,
    isResolved AS is_resolved,
    probability AS prob,
    volume,
    totalLiquidity AS liquidity_total,
    timestamp_millis(createdTime) AS created_at,
    timestamp_millis(closeTime) AS closed_at,
    timestamp_millis(resolutionTime) AS resolved_at,
    -- try_cast: Spark SQL has the same try_cast semantics as DuckDB's
    -- (NULL on a bad value instead of raising), a direct port of the
    -- original macro, not an approximation.
    try_cast(sportsStartTimestamp AS timestamp) AS sports_start_at
  FROM ${catalog}.raw.markets
)
SELECT
  *,
  COUNT(*) OVER (PARTITION BY market_id) = 1 AS dedup_ok
FROM base
