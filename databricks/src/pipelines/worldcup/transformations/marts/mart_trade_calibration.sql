-- Port of dbt/models/marts/mart_trade_calibration.sql. Replicates
-- Manifold's own published calibration methodology (manifold.markets/calibration)
-- for an apples-to-apples Brier score comparison: one row per real trade on
-- a resolved BINARY market with >=15 distinct traders, predicted probability
-- = average of before/after each trade. Uses every qualifying trade rather
-- than Manifold's own 2% sample -- a performance tradeoff on their side that
-- doesn't apply at this dataset's scale, more precise, not a methodology
-- deviation.
CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.marts.mart_trade_calibration (
  CONSTRAINT bet_id_not_null EXPECT (bet_id IS NOT NULL) ON VIOLATION FAIL UPDATE,
  CONSTRAINT bet_id_unique EXPECT (dedup_ok) ON VIOLATION FAIL UPDATE,
  CONSTRAINT market_id_not_null EXPECT (market_id IS NOT NULL) ON VIOLATION FAIL UPDATE,
  CONSTRAINT is_yes_not_null EXPECT (is_yes IS NOT NULL) ON VIOLATION FAIL UPDATE,
  CONSTRAINT prob_trade_not_null EXPECT (prob_trade IS NOT NULL) ON VIOLATION FAIL UPDATE,
  CONSTRAINT prob_bucket_not_null EXPECT (prob_bucket IS NOT NULL) ON VIOLATION FAIL UPDATE
)
AS
WITH binary_markets AS (
  SELECT
    market_id,
    resolution = 'YES' AS is_yes
  FROM ${catalog}.staging.stg_manifold_markets
  WHERE outcome_type = 'BINARY'
    AND resolution IN ('YES', 'NO')
),

trader_counts AS (
  SELECT
    market_id,
    count(DISTINCT user_id) AS trader_count
  FROM ${catalog}.staging.stg_manifold_bets
  WHERE answer_id IS NULL
  GROUP BY 1
),

qualifying_markets AS (
  SELECT
    bm.market_id,
    bm.is_yes
  FROM binary_markets bm
  INNER JOIN trader_counts tc ON bm.market_id = tc.market_id
  WHERE tc.trader_count >= 15
),

base AS (
  SELECT
    b.bet_id,
    b.market_id,
    qm.is_yes,
    (b.prob_before + b.prob_after) / 2 AS prob_trade,
    least(floor(((b.prob_before + b.prob_after) / 2) * 10) / 10, 0.9) AS prob_bucket
  FROM ${catalog}.staging.stg_manifold_bets b
  INNER JOIN qualifying_markets qm ON b.market_id = qm.market_id
  WHERE b.answer_id IS NULL
)

SELECT
  *,
  COUNT(*) OVER (PARTITION BY bet_id) = 1 AS dedup_ok
FROM base
