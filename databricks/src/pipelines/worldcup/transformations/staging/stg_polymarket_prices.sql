-- Port of dbt/models/staging/stg_polymarket_prices.sql. Primary source for
-- Polymarket probability reconstruction (ADR-0011): full-history, hourly
-- price samples, not the 10,000-record-capped /trades endpoint.
--
-- timestamp_seconds(), not to_timestamp() -- see stg_polymarket_trades.sql
-- for why.
CREATE OR REFRESH MATERIALIZED VIEW stg_polymarket_prices (
  CONSTRAINT market_id_not_null EXPECT (market_id IS NOT NULL) ON VIOLATION FAIL UPDATE,
  CONSTRAINT created_at_not_null EXPECT (created_at IS NOT NULL) ON VIOLATION FAIL UPDATE,
  CONSTRAINT price_not_null EXPECT (price IS NOT NULL) ON VIOLATION FAIL UPDATE
)
AS
SELECT
  market_id,
  condition_id,
  token_id,
  timestamp_seconds(t) AS created_at,
  p AS price
FROM ${catalog}.raw.polymarket_prices
