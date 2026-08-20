-- Port of dbt/models/intermediate/int_answer_kickoff_times.sql. Fans
-- int_market_kickoff_times' market-level kickoff times out to every real
-- answer_id under that market (ADR-0009), so every consumer joins against
-- a real (market_id, answer_id) pair.
CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.intermediate.int_answer_kickoff_times (
  CONSTRAINT market_answer_unique EXPECT (dedup_ok) ON VIOLATION FAIL UPDATE,
  CONSTRAINT answer_id_not_null EXPECT (answer_id IS NOT NULL) ON VIOLATION FAIL UPDATE,
  CONSTRAINT openfootball_kickoff_at_not_null EXPECT (openfootball_kickoff_at IS NOT NULL) ON VIOLATION FAIL UPDATE
)
AS
WITH market_level_kickoffs AS (
  SELECT
    k.market_id,
    p.answer_id,
    k.openfootball_kickoff_at,
    k.round,
    k.schedule_team1,
    k.schedule_team2
  FROM ${catalog}.intermediate.int_market_kickoff_times k
  INNER JOIN (
    SELECT DISTINCT market_id, answer_id
    FROM ${catalog}.intermediate.int_market_implied_probability
  ) p
    ON k.market_id = p.market_id
  WHERE k.answer_id IS NULL
),

answer_level_kickoffs AS (
  SELECT
    market_id,
    answer_id,
    openfootball_kickoff_at,
    round,
    schedule_team1,
    schedule_team2
  FROM ${catalog}.intermediate.int_market_kickoff_times
  WHERE answer_id IS NOT NULL
),

unioned AS (
  SELECT * FROM market_level_kickoffs
  UNION ALL
  SELECT * FROM answer_level_kickoffs
)

SELECT
  *,
  COUNT(*) OVER (PARTITION BY market_id, answer_id) = 1 AS dedup_ok
FROM unioned
