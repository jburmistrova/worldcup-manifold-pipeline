-- Port of dbt/models/intermediate/int_all_market_ticks.sql. Unions every
-- platform's price-reconstruction-worthy events into one canonical shape
-- (ADR-0011/ADR-0012), so int_market_implied_probability's own logic
-- doesn't need to know which platform a row came from. Manifold contributes
-- real prob_before/prob_after pairs unchanged; Polymarket's are LAG-derived
-- per (market, answer), validated sound for Polymarket specifically in the
-- original build (no cross-answer AMM coupling the way Manifold's
-- cpmm-multi-1 markets have).
--
-- Publishes to intermediate (not the pipeline's default staging schema).
-- Every FROM reference below is fully qualified too, not just the CREATE
-- target: verified empirically (not per SDP's own documented convention,
-- which turned out not to hold once a pipeline spans multiple schemas) that
-- a bare sibling-dataset name resolves against the pipeline's *default*
-- schema (staging) regardless of which schema the referencing file itself
-- publishes to -- a real, load-bearing DLT behavior this port only found by
-- running it and reading the resulting TABLE_OR_VIEW_NOT_FOUND errors. See
-- ADR-0016.
--
-- Always includes Polymarket in this deployment -- see ADR-0016 for why
-- dbt's INCLUDE_POLYMARKET env-var toggle (build-time, per dbt run) has no
-- clean equivalent in DLT's statically-defined DAG, and isn't reproduced
-- here.
CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.intermediate.int_all_market_ticks (
  CONSTRAINT market_id_not_null EXPECT (market_id IS NOT NULL) ON VIOLATION FAIL UPDATE,
  CONSTRAINT bet_id_not_null EXPECT (bet_id IS NOT NULL) ON VIOLATION FAIL UPDATE,
  CONSTRAINT bet_id_unique EXPECT (dedup_ok) ON VIOLATION FAIL UPDATE,
  CONSTRAINT created_at_not_null EXPECT (created_at IS NOT NULL) ON VIOLATION FAIL UPDATE,
  CONSTRAINT prob_after_not_null EXPECT (prob_after IS NOT NULL) ON VIOLATION FAIL UPDATE,
  CONSTRAINT source_platform_valid EXPECT (source_platform IN ('manifold', 'polymarket')) ON VIOLATION FAIL UPDATE
)
AS
WITH manifold_ticks AS (
  SELECT
    market_id,
    answer_id,
    bet_id,
    created_at,
    amount,
    prob_before,
    prob_after,
    'manifold' AS source_platform
  FROM ${catalog}.staging.stg_manifold_bets
),

polymarket_ticks AS (
  SELECT
    m.market_id,
    m.answer_id,
    -- includes market_id/answer_id, not a bare row_number(): row_number()
    -- resets per partition, so a bare counter alone collides across every
    -- Polymarket market -- a real bug the original build caught via its own
    -- uniqueness test (8,882 duplicates on the first run), not assumed safe.
    concat('pm-', m.market_id, '-', coalesce(m.answer_id, 'x'), '-',
      cast(row_number() OVER (PARTITION BY m.market_id, m.answer_id ORDER BY p.created_at) AS string)) AS bet_id,
    p.created_at,
    cast(null AS double) AS amount,
    lag(p.price) OVER (PARTITION BY m.market_id, m.answer_id ORDER BY p.created_at) AS prob_before,
    p.price AS prob_after,
    'polymarket' AS source_platform
  FROM ${catalog}.staging.stg_polymarket_prices p
  INNER JOIN ${catalog}.staging.stg_polymarket_markets m
    ON p.condition_id = m.condition_id
),

unioned AS (
  SELECT * FROM manifold_ticks
  UNION ALL
  SELECT * FROM polymarket_ticks
)

SELECT
  *,
  COUNT(*) OVER (PARTITION BY bet_id) = 1 AS dedup_ok
FROM unioned
