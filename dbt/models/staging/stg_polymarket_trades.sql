-- Yes-side trades only (outcomeIndex = 0, confirmed empirically to always
-- be "Yes"). No-side trades on the same market are the complementary view
-- of the same information (a SELL of Yes at 0.999 is roughly a BUY of No
-- at 0.001), not new data, matching the same Yes-only convention
-- pull_polymarket_prices.py already uses and Manifold's own
-- prob = P(YES) convention.
--
-- trade_id is synthesized (Polymarket's trade payload has no single id
-- field): a hash over every field that could distinguish two real fills,
-- not just transactionHash, since one on-chain transaction can settle
-- multiple separate fills atomically.
--
-- Real, not full-history: /trades caps at the 10,000 most recent records
-- per market with no way to page further back (ADR-0011). This staging
-- model is complete relative to what was ingested, not relative to a
-- market's actual full trading history; that gap is why
-- stg_polymarket_prices exists as the primary reconstruction source, not
-- this one.

select
    md5(
        transactionHash || '|' || conditionId || '|' || asset || '|' || side
        || '|' || cast(size as varchar) || '|' || cast(price as varchar)
        || '|' || cast(timestamp as varchar)
    ) as trade_id,
    conditionId as condition_id,
    asset as token_id,
    side,
    size,
    price,
    -- cast to plain TIMESTAMP, not TIMESTAMP WITH TIME ZONE: see the same
    -- note in stg_polymarket_prices.sql, this matters once these feed a
    -- shared union with Manifold's own UTC-naive timestamps.
    cast(to_timestamp(timestamp) as timestamp) as created_at
from {{ source('polymarket_raw', 'polymarket_trades') }}
where outcomeIndex = 0
