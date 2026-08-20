-- Port of dbt/models/staging/stg_manifold_bets.sql: real, filled,
-- non-cancelled, nonzero-amount trades only (same three business-logic
-- exclusions the original model documents -- cancelled limit orders,
-- unfilled orders, and zero-amount system-generated share allocations at
-- market/answer creation).
--
-- Deliberately a Materialized View, NOT a Streaming Table, even though the
-- dbt original is this project's one deliberately-incremental model. The
-- underlying bronze table (${catalog}.raw.bets) is fully overwritten by
-- flatten_to_delta.py on every ingestion run, not a genuinely
-- incrementally-arriving file stream -- modeling it as a Streaming Table
-- would claim an append-only semantics that isn't actually true of the
-- source. See ADR-0016 for the full reasoning; this is a real, deliberate
-- divergence from the dbt original, not an oversight.
CREATE OR REFRESH MATERIALIZED VIEW stg_manifold_bets (
  CONSTRAINT bet_id_not_null EXPECT (bet_id IS NOT NULL) ON VIOLATION FAIL UPDATE,
  CONSTRAINT bet_id_unique EXPECT (dedup_ok) ON VIOLATION FAIL UPDATE,
  CONSTRAINT market_id_not_null EXPECT (market_id IS NOT NULL) ON VIOLATION FAIL UPDATE
)
AS
WITH base AS (
  SELECT
    id AS bet_id,
    contractId AS market_id,
    answerId AS answer_id,
    userId AS user_id,
    outcome,
    amount,
    orderAmount AS amount_order,
    shares AS count_share,
    probBefore AS prob_before,
    probAfter AS prob_after,
    limitProb AS prob_limit,
    timestamp_millis(createdTime) AS created_at,
    isFilled AS is_filled,
    isCancelled AS is_cancelled,
    isRedemption AS is_redemption
  FROM ${catalog}.raw.bets
  WHERE isFilled = true
    AND isCancelled = false
    AND amount != 0
)
SELECT
  *,
  COUNT(*) OVER (PARTITION BY bet_id) = 1 AS dedup_ok
FROM base
