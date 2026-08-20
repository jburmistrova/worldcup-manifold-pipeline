-- Port of dbt/models/intermediate/int_pre_kickoff_probability.sql. For
-- each market/answer with a validated kickoff time, the market's implied
-- probability from its LAST real trade strictly before kickoff -- what the
-- market believed right before the game started, the original problem
-- statement's actual question (docs/architecture.md), not a resolution-time
-- snapshot.
CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.intermediate.int_pre_kickoff_probability (
  CONSTRAINT market_answer_unique EXPECT (dedup_ok) ON VIOLATION FAIL UPDATE,
  CONSTRAINT pre_kickoff_prob_not_null EXPECT (pre_kickoff_prob IS NOT NULL) ON VIOLATION FAIL UPDATE
)
AS
WITH pre_kickoff_ticks AS (
  SELECT
    p.market_id,
    p.answer_id,
    p.created_at,
    p.prob_after,
    row_number() OVER (
      PARTITION BY p.market_id, p.answer_id
      ORDER BY p.created_at DESC
    ) AS recency_rank
  FROM ${catalog}.intermediate.int_market_implied_probability p
  INNER JOIN ${catalog}.intermediate.int_answer_kickoff_times k
    ON p.market_id = k.market_id
    AND p.answer_id = k.answer_id
  WHERE p.created_at <= k.openfootball_kickoff_at
),

latest AS (
  SELECT
    market_id,
    answer_id,
    created_at AS last_trade_before_kickoff_at,
    prob_after AS pre_kickoff_prob
  FROM pre_kickoff_ticks
  WHERE recency_rank = 1
)

SELECT
  *,
  COUNT(*) OVER (PARTITION BY market_id, answer_id) = 1 AS dedup_ok
FROM latest
