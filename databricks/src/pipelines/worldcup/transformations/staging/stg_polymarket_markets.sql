-- Port of dbt/models/staging/stg_polymarket_markets.sql. Same negRisk
-- grouping (ADR-0011) as the original: a market with a negRiskMarketID
-- belongs to a group (canonical market_id = the group id, answer_id = this
-- market's own raw id); a standalone market keeps answer_id NULL, same as
-- a Manifold BINARY market.
--
-- json_extract_string(...) (DuckDB) -> get_json_object(...) (Spark SQL):
-- same JSONPath syntax ($[0], $[1] for array index), a direct port.
--
-- Always included in this deployment (Polymarket ingestion always runs
-- here) -- see ADR-0016 for why dbt's INCLUDE_POLYMARKET env-var toggle
-- has no static-DAG equivalent in DLT and isn't reproduced.
CREATE OR REFRESH MATERIALIZED VIEW stg_polymarket_markets (
  CONSTRAINT condition_id_not_null EXPECT (condition_id IS NOT NULL) ON VIOLATION FAIL UPDATE,
  CONSTRAINT condition_id_unique EXPECT (condition_id_dedup_ok) ON VIOLATION FAIL UPDATE,
  CONSTRAINT question_not_null EXPECT (question IS NOT NULL) ON VIOLATION FAIL UPDATE,
  CONSTRAINT market_answer_unique EXPECT (market_answer_dedup_ok) ON VIOLATION FAIL UPDATE
)
AS
WITH base AS (
  SELECT
    coalesce(neg_risk_market_id, market_id) AS market_id,
    CASE WHEN neg_risk_market_id IS NOT NULL THEN market_id END AS answer_id,
    market_id AS polymarket_market_id,
    condition_id,
    question,
    groupItemTitle AS answer_text,
    'BINARY' AS outcome_type,
    CASE
      WHEN closed AND get_json_object(outcome_prices, '$[0]') = '1' THEN 'YES'
      WHEN closed AND get_json_object(outcome_prices, '$[1]') = '1' THEN 'NO'
    END AS resolution,
    closed AS is_resolved,
    cast(get_json_object(outcome_prices, '$[0]') AS double) AS prob,
    volume,
    liquidity AS liquidity_total,
    try_cast(created_at AS timestamp) AS created_at,
    try_cast(closed_time AS timestamp) AS closed_at,
    try_cast(closed_time AS timestamp) AS resolved_at,
    get_json_object(clob_token_ids, '$[0]') AS yes_token_id
  FROM ${catalog}.raw.polymarket_markets
)
SELECT
  *,
  COUNT(*) OVER (PARTITION BY condition_id) = 1 AS condition_id_dedup_ok,
  COUNT(*) OVER (PARTITION BY market_id, answer_id) = 1 AS market_answer_dedup_ok
FROM base
