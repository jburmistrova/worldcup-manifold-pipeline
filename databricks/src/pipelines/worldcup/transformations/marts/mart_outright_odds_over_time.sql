-- Port of dbt/models/marts/mart_outright_odds_over_time.sql. How the
-- tournament-winner outright contract repriced over the tournament, scoped
-- to the one Manifold market with real trading activity behind it out of
-- ~15 near-duplicates ($1.65M volume, 18,293 bets -- see ADR-0009), not
-- assumed, checked.
CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.marts.mart_outright_odds_over_time (
  CONSTRAINT bet_id_unique EXPECT (dedup_ok) ON VIOLATION FAIL UPDATE,
  CONSTRAINT market_id_not_null EXPECT (market_id IS NOT NULL) ON VIOLATION FAIL UPDATE,
  CONSTRAINT answer_id_not_null EXPECT (answer_id IS NOT NULL) ON VIOLATION FAIL UPDATE,
  CONSTRAINT team_not_null EXPECT (team IS NOT NULL) ON VIOLATION FAIL UPDATE,
  CONSTRAINT is_winner_not_null EXPECT (is_winner IS NOT NULL) ON VIOLATION FAIL UPDATE,
  CONSTRAINT bet_id_not_null EXPECT (bet_id IS NOT NULL) ON VIOLATION FAIL UPDATE,
  CONSTRAINT created_at_not_null EXPECT (created_at IS NOT NULL) ON VIOLATION FAIL UPDATE,
  CONSTRAINT tick_number_not_null EXPECT (tick_number IS NOT NULL) ON VIOLATION FAIL UPDATE,
  CONSTRAINT prob_before_not_null EXPECT (prob_before IS NOT NULL) ON VIOLATION FAIL UPDATE,
  CONSTRAINT prob_after_not_null EXPECT (prob_after IS NOT NULL) ON VIOLATION FAIL UPDATE,
  CONSTRAINT prob_vwap_running_not_null EXPECT (prob_vwap_running IS NOT NULL) ON VIOLATION FAIL UPDATE,
  CONSTRAINT jump_rank_not_null EXPECT (jump_rank IS NOT NULL) ON VIOLATION FAIL UPDATE
)
AS
WITH base AS (
  SELECT
    p.market_id,
    p.answer_id,
    a.answer_text AS team,
    p.answer_id = m.resolution AS is_winner,
    p.bet_id,
    p.created_at,
    p.tick_number,
    p.prob_before,
    p.prob_after,
    p.prob_vwap_running,
    p.jump_rank
  FROM ${catalog}.intermediate.int_market_implied_probability p
  INNER JOIN ${catalog}.staging.stg_manifold_market_answers a
    ON p.market_id = a.market_id
    AND p.answer_id = a.answer_id
  INNER JOIN ${catalog}.staging.stg_manifold_markets m
    ON p.market_id = m.market_id
  WHERE p.market_id = 'JRzL2QcArhM674YSO4d8'
)
SELECT
  *,
  COUNT(*) OVER (PARTITION BY bet_id) = 1 AS dedup_ok
FROM base
