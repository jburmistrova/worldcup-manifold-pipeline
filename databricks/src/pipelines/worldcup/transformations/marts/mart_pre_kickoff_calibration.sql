-- Port of dbt/models/marts/mart_pre_kickoff_calibration.sql. The genuine
-- pre-kickoff calibration comparison (vs. mart_market_efficiency's
-- resolution-time snapshot), for the subset of predictions with a
-- validated kickoff time and a real trade before it.
CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.marts.mart_pre_kickoff_calibration (
  CONSTRAINT market_answer_unique EXPECT (dedup_ok) ON VIOLATION FAIL UPDATE,
  CONSTRAINT market_id_not_null EXPECT (market_id IS NOT NULL) ON VIOLATION FAIL UPDATE,
  CONSTRAINT predicted_prob_not_null EXPECT (predicted_prob IS NOT NULL) ON VIOLATION FAIL UPDATE,
  CONSTRAINT is_yes_not_null EXPECT (is_yes IS NOT NULL) ON VIOLATION FAIL UPDATE,
  CONSTRAINT prob_bucket_not_null EXPECT (prob_bucket IS NOT NULL) ON VIOLATION FAIL UPDATE
)
AS
WITH base AS (
  SELECT
    a.market_id,
    a.answer_id,
    a.answer_text AS label,
    p.pre_kickoff_prob AS predicted_prob,
    CASE
      WHEN m.resolution = 'MKT' THEN a.resolution = 'YES'
      ELSE a.answer_id = m.resolution
    END AS is_yes,
    a.volume,
    a.liquidity_total,
    least(floor(p.pre_kickoff_prob * 10) / 10, 0.9) AS prob_bucket
  FROM ${catalog}.staging.stg_manifold_market_answers a
  INNER JOIN ${catalog}.staging.stg_manifold_markets m
    ON a.market_id = m.market_id
  INNER JOIN ${catalog}.intermediate.int_pre_kickoff_probability p
    ON a.market_id = p.market_id
    AND a.answer_id = p.answer_id
  WHERE
    (m.resolution = 'MKT' AND a.resolution IN ('YES', 'NO'))
    OR (
      m.resolution NOT IN ('CANCEL', 'MKT', 'CHOOSE_MULTIPLE')
      AND EXISTS (
        SELECT 1 FROM ${catalog}.staging.stg_manifold_market_answers a2
        WHERE a2.market_id = m.market_id AND a2.answer_id = m.resolution
      )
    )
)
SELECT
  *,
  COUNT(*) OVER (PARTITION BY market_id, answer_id) = 1 AS dedup_ok
FROM base
