-- Port of dbt/models/staging/stg_manifold_market_answers.sql.
CREATE OR REFRESH MATERIALIZED VIEW stg_manifold_market_answers (
  CONSTRAINT answer_id_not_null EXPECT (answer_id IS NOT NULL) ON VIOLATION FAIL UPDATE,
  CONSTRAINT answer_id_unique EXPECT (dedup_ok) ON VIOLATION FAIL UPDATE,
  CONSTRAINT market_id_not_null EXPECT (market_id IS NOT NULL) ON VIOLATION FAIL UPDATE
)
AS
WITH base AS (
  SELECT
    contractId AS market_id,
    id AS answer_id,
    index AS answer_index,
    text AS answer_text,
    isOther AS is_other,
    probability AS prob,
    resolution,
    resolutionProbability AS prob_resolution,
    volume,
    totalLiquidity AS liquidity_total,
    timestamp_millis(createdTime) AS created_at,
    timestamp_millis(resolutionTime) AS resolved_at
  FROM ${catalog}.raw.market_answers
)
SELECT
  *,
  COUNT(*) OVER (PARTITION BY answer_id) = 1 AS dedup_ok
FROM base
