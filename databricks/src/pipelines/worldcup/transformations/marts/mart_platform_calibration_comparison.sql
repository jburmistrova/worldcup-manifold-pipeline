-- Port of dbt/models/marts/mart_platform_calibration_comparison.sql.
-- Real-money (Polymarket) vs. play-money (Manifold) calibration comparison,
-- one row per team's outright-winner prediction on each platform, at the
-- last real tick strictly before the tournament itself started
-- (2026-06-11 19:00 UTC, ADR-0013). Always included in this deployment --
-- see ADR-0016 for why dbt's INCLUDE_POLYMARKET toggle isn't reproduced.
CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.marts.mart_platform_calibration_comparison (
  CONSTRAINT platform_team_unique EXPECT (dedup_ok) ON VIOLATION FAIL UPDATE,
  CONSTRAINT source_platform_valid EXPECT (source_platform IN ('manifold', 'polymarket')) ON VIOLATION FAIL UPDATE,
  CONSTRAINT team_not_null EXPECT (team IS NOT NULL) ON VIOLATION FAIL UPDATE,
  CONSTRAINT predicted_prob_not_null EXPECT (predicted_prob IS NOT NULL) ON VIOLATION FAIL UPDATE,
  CONSTRAINT is_yes_not_null EXPECT (is_yes IS NOT NULL) ON VIOLATION FAIL UPDATE
)
AS
WITH manifold_pre_tournament_ticks AS (
  SELECT
    market_id,
    answer_id,
    prob_after,
    row_number() OVER (
      PARTITION BY market_id, answer_id
      ORDER BY created_at DESC
    ) AS recency_rank
  FROM ${catalog}.intermediate.int_market_implied_probability
  WHERE market_id = 'JRzL2QcArhM674YSO4d8'
    AND created_at < timestamp'2026-06-11 19:00:00'
),

manifold_outcomes AS (
  SELECT
    a.market_id,
    a.answer_id,
    a.answer_text AS team,
    a.answer_id = m.resolution AS is_yes
  FROM ${catalog}.staging.stg_manifold_market_answers a
  INNER JOIN ${catalog}.staging.stg_manifold_markets m
    ON a.market_id = m.market_id
  WHERE a.market_id = 'JRzL2QcArhM674YSO4d8'
),

polymarket_pre_tournament_ticks AS (
  SELECT
    market_id,
    answer_id,
    prob_after,
    row_number() OVER (
      PARTITION BY market_id, answer_id
      ORDER BY created_at DESC
    ) AS recency_rank
  FROM ${catalog}.intermediate.int_market_implied_probability
  WHERE market_id = '0xb5c32a9acd39848acad4913ac4cd49c5de2afcc9d23a8a7ba2419375fab87400'
    AND created_at < timestamp'2026-06-11 19:00:00'
),

polymarket_outcomes AS (
  SELECT
    market_id,
    answer_id,
    answer_text AS team,
    resolution = 'YES' AS is_yes
  FROM ${catalog}.staging.stg_polymarket_markets
  WHERE market_id = '0xb5c32a9acd39848acad4913ac4cd49c5de2afcc9d23a8a7ba2419375fab87400'
    AND resolution IN ('YES', 'NO')
),

manifold_rows AS (
  SELECT
    'manifold' AS source_platform,
    o.team,
    t.prob_after AS predicted_prob,
    o.is_yes
  FROM manifold_pre_tournament_ticks t
  INNER JOIN manifold_outcomes o
    ON t.market_id = o.market_id AND t.answer_id = o.answer_id
  WHERE t.recency_rank = 1
),

polymarket_rows AS (
  SELECT
    'polymarket' AS source_platform,
    o.team,
    t.prob_after AS predicted_prob,
    o.is_yes
  FROM polymarket_pre_tournament_ticks t
  INNER JOIN polymarket_outcomes o
    ON t.market_id = o.market_id AND t.answer_id = o.answer_id
  WHERE t.recency_rank = 1
),

unioned AS (
  SELECT * FROM manifold_rows
  UNION ALL
  SELECT * FROM polymarket_rows
)

SELECT
  *,
  COUNT(*) OVER (PARTITION BY source_platform, team) = 1 AS dedup_ok
FROM unioned
