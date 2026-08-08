-- Full-history, hourly-cadence price series per market, the primary source
-- for Polymarket probability reconstruction (see ADR-0011 for why /trades
-- isn't: its 10,000-record cap can reach back only hours on a popular
-- market, not the pre-kickoff-era history this project's calibration work
-- needs). Already scoped to the Yes-side token only at ingestion time
-- (pull_polymarket_prices.py only ever requests clobTokenIds[0]).
--
-- No amount/size here, unlike a real trade: this is a sampled price
-- snapshot, not an executed fill. int_market_implied_probability's VWAP
-- weighting has nothing to weight by for these rows; left genuinely NULL
-- downstream rather than faked with an equal weight.

select
    market_id,
    condition_id,
    token_id,
    -- to_timestamp() returns TIMESTAMP WITH TIME ZONE; cast to plain
    -- TIMESTAMP so this matches Manifold's own epoch_ms()-derived columns
    -- exactly (both UTC-naive), a real mismatch caught by a contract
    -- failure once this fed into the shared int_all_market_ticks union,
    -- not assumed compatible just because both represent "UTC" in spirit.
    cast(to_timestamp(t) as timestamp) as created_at,
    p as price
from {{ source('polymarket_raw', 'polymarket_prices') }}
