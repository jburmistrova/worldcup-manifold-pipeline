-- Port of dbt/models/staging/stg_polymarket_trades.sql. Yes-side trades
-- only (outcomeIndex = 0). trade_id synthesized via md5 over every
-- field that could distinguish two real fills, same as the original.
--
-- timestamp_seconds(), not to_timestamp(): DuckDB's to_timestamp(epoch_secs)
-- takes epoch SECONDS directly; Spark SQL's to_timestamp() expects a string
-- or doesn't reliably parse a bare numeric the same way. timestamp_seconds()
-- is Spark's actual defined bigint-epoch-seconds-to-timestamp function --
-- verified against Spark's docs, not assumed equivalent from the name alone.
CREATE OR REFRESH MATERIALIZED VIEW stg_polymarket_trades (
  CONSTRAINT trade_id_unique EXPECT (dedup_ok) ON VIOLATION FAIL UPDATE,
  CONSTRAINT condition_id_not_null EXPECT (condition_id IS NOT NULL) ON VIOLATION FAIL UPDATE,
  CONSTRAINT price_not_null EXPECT (price IS NOT NULL) ON VIOLATION FAIL UPDATE
)
AS
WITH base AS (
  SELECT
    md5(
      concat_ws('|', transactionHash, conditionId, asset, side,
        cast(size AS string), cast(price AS string), cast(timestamp AS string))
    ) AS trade_id,
    conditionId AS condition_id,
    asset AS token_id,
    side,
    size,
    price,
    timestamp_seconds(timestamp) AS created_at
  FROM ${catalog}.raw.polymarket_trades
  WHERE outcomeIndex = 0
)
SELECT
  *,
  COUNT(*) OVER (PARTITION BY trade_id) = 1 AS dedup_ok
FROM base
