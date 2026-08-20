-- Port of dbt/models/marts/mart_match_price_history.sql. No new
-- reconstruction: scopes int_market_implied_probability down to genuine
-- single matches (via int_answer_kickoff_times) and attaches team names +
-- kickoff time for a readable price path.
CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.marts.mart_match_price_history (
  CONSTRAINT bet_id_unique EXPECT (dedup_ok) ON VIOLATION FAIL UPDATE,
  CONSTRAINT market_id_not_null EXPECT (market_id IS NOT NULL) ON VIOLATION FAIL UPDATE,
  CONSTRAINT schedule_team1_not_null EXPECT (schedule_team1 IS NOT NULL) ON VIOLATION FAIL UPDATE,
  CONSTRAINT schedule_team2_not_null EXPECT (schedule_team2 IS NOT NULL) ON VIOLATION FAIL UPDATE,
  CONSTRAINT openfootball_kickoff_at_not_null EXPECT (openfootball_kickoff_at IS NOT NULL) ON VIOLATION FAIL UPDATE,
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
    k.schedule_team1,
    k.schedule_team2,
    k.round,
    k.openfootball_kickoff_at,
    p.bet_id,
    p.created_at,
    p.tick_number,
    p.prob_before,
    p.prob_after,
    p.prob_vwap_running,
    p.jump_rank
  FROM ${catalog}.intermediate.int_market_implied_probability p
  INNER JOIN ${catalog}.intermediate.int_answer_kickoff_times k
    ON p.market_id = k.market_id
    AND p.answer_id = k.answer_id
)
SELECT
  *,
  COUNT(*) OVER (PARTITION BY bet_id) = 1 AS dedup_ok
FROM base
