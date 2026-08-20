-- Port of dbt/models/marts/mart_market_efficiency.sql. One row per resolved
-- prediction (BINARY market or MULTIPLE_CHOICE answer) with its
-- resolution-time predicted probability, actual outcome, and a decile
-- bucket -- the core calibration / favorite-longshot-bias table this
-- project's Brier score numbers are computed from.
--
-- Decile bucket formula (least(floor(x * 10) / 10, 0.9)) ported inline,
-- matching dbt/macros/prob_bucket.sql exactly -- SDP SQL has no dbt-style
-- macro system, so this repeats verbatim in every mart that needs it
-- (mart_market_efficiency, mart_pre_kickoff_calibration, mart_trade_calibration),
-- a real, deliberate duplication cost of the port, not an oversight. See
-- ADR-0016.
--
-- relationships (referential integrity, dbt's `relationships` test) has no
-- direct DLT expectation equivalent. A `CONSTRAINT ... EXPECT (col IN
-- (SELECT ... FROM sibling_table))` was tried here and confirmed, by
-- actually running it, NOT to work: it breaks the pipeline's own flow
-- resolution outright (`TABLE_OR_VIEW_NOT_FOUND` on the referenced
-- table, even though that table is a genuine sibling in this same
-- pipeline and does get built) -- a subquery inside an EXPECT clause
-- doesn't register as a real dependency edge in DLT's DAG the way a FROM
-- clause does, so the constrained flow gets analyzed before its subquery
-- dependency is guaranteed to exist. Removed rather than forced to work;
-- this referential-integrity check simply has no working DLT equivalent
-- today. Full finding in ADR-0016, a real, load-bearing DLT gap, not a
-- hidden one.
CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.marts.mart_market_efficiency (
  CONSTRAINT market_answer_unique EXPECT (dedup_ok) ON VIOLATION FAIL UPDATE,
  CONSTRAINT market_id_not_null EXPECT (market_id IS NOT NULL) ON VIOLATION FAIL UPDATE,
  CONSTRAINT predicted_prob_not_null EXPECT (predicted_prob IS NOT NULL) ON VIOLATION FAIL UPDATE,
  CONSTRAINT is_yes_not_null EXPECT (is_yes IS NOT NULL) ON VIOLATION FAIL UPDATE,
  CONSTRAINT prob_bucket_not_null EXPECT (prob_bucket IS NOT NULL) ON VIOLATION FAIL UPDATE
)
AS
WITH binary_predictions AS (
  SELECT
    market_id,
    cast(null AS string) AS answer_id,
    question AS label,
    prob AS predicted_prob,
    resolution = 'YES' AS is_yes,
    volume,
    liquidity_total
  FROM ${catalog}.staging.stg_manifold_markets
  WHERE outcome_type = 'BINARY'
    AND resolution IN ('YES', 'NO')
),

multiple_choice_predictions AS (
  -- single-select MULTIPLE_CHOICE markets never set a.resolution; the
  -- winner is the market's own resolution field holding the winning
  -- answer_id directly (see lessons_learned.md).
  SELECT
    a.market_id,
    a.answer_id,
    a.answer_text AS label,
    a.prob_resolution AS predicted_prob,
    CASE
      WHEN m.resolution = 'MKT' THEN a.resolution = 'YES'
      ELSE a.answer_id = m.resolution
    END AS is_yes,
    a.volume,
    a.liquidity_total
  FROM ${catalog}.staging.stg_manifold_market_answers a
  INNER JOIN ${catalog}.staging.stg_manifold_markets m
    ON a.market_id = m.market_id
  WHERE
    a.prob_resolution IS NOT NULL
    AND (
      (m.resolution = 'MKT' AND a.resolution IN ('YES', 'NO'))
      OR (
        m.resolution NOT IN ('CANCEL', 'MKT', 'CHOOSE_MULTIPLE')
        AND EXISTS (
          SELECT 1 FROM ${catalog}.staging.stg_manifold_market_answers a2
          WHERE a2.market_id = m.market_id AND a2.answer_id = m.resolution
        )
      )
    )
),

unioned AS (
  SELECT * FROM binary_predictions
  UNION ALL
  SELECT * FROM multiple_choice_predictions
),

bucketed AS (
  SELECT
    market_id,
    answer_id,
    label,
    predicted_prob,
    is_yes,
    volume,
    liquidity_total,
    least(floor(predicted_prob * 10) / 10, 0.9) AS prob_bucket
  FROM unioned
)

SELECT
  *,
  COUNT(*) OVER (PARTITION BY market_id, answer_id) = 1 AS dedup_ok
FROM bucketed
