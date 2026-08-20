-- Port of dbt/models/intermediate/int_market_implied_probability.sql.
-- Reconstructs the probability path per (market_id, answer_id): running
-- VWAP and a repricing-jump rank. Reads int_all_market_ticks, not staging
-- directly (ADR-0011/0012) -- Polymarket's NULL amount rows correctly stay
-- NULL in prob_vwap_running via SQL's own NULL handling in SUM(), same as
-- the dbt original, no special case needed here either.
CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.intermediate.int_market_implied_probability (
  CONSTRAINT bet_id_not_null EXPECT (bet_id IS NOT NULL) ON VIOLATION FAIL UPDATE,
  CONSTRAINT bet_id_unique EXPECT (dedup_ok) ON VIOLATION FAIL UPDATE,
  CONSTRAINT market_id_not_null EXPECT (market_id IS NOT NULL) ON VIOLATION FAIL UPDATE,
  CONSTRAINT tick_number_not_null EXPECT (tick_number IS NOT NULL) ON VIOLATION FAIL UPDATE
)
AS
WITH ordered_bets AS (
  SELECT
    market_id,
    answer_id,
    bet_id,
    created_at,
    amount,
    prob_before,
    prob_after,
    prob_after - prob_before AS prob_change,
    row_number() OVER (
      PARTITION BY market_id, answer_id
      ORDER BY created_at
    ) AS tick_number
  FROM ${catalog}.intermediate.int_all_market_ticks
),

computed AS (
  SELECT
    market_id,
    answer_id,
    bet_id,
    created_at,
    tick_number,
    amount,
    prob_before,
    prob_after,
    prob_change,

    sum(((prob_before + prob_after) / 2) * abs(amount)) OVER (
      PARTITION BY market_id, answer_id
      ORDER BY created_at
      ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) / sum(abs(amount)) OVER (
      PARTITION BY market_id, answer_id
      ORDER BY created_at
      ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS prob_vwap_running,

    rank() OVER (
      PARTITION BY market_id, answer_id
      ORDER BY abs(prob_change) DESC
    ) AS jump_rank

  FROM ordered_bets
)

SELECT
  *,
  COUNT(*) OVER (PARTITION BY bet_id) = 1 AS dedup_ok
FROM computed
