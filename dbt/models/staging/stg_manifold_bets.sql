-- Real, filled, non-cancelled trades only. Cancelled limit orders and share
-- redemptions are excluded here — this is a business-logic decision (what
-- counts as a "real" trade), so it belongs at the staging layer, tested,
-- not silently baked into ingestion (see ADR-0005, docs/data_dictionary.md).
select
    id as bet_id,
    contractId as market_id,
    userId as user_id,
    outcome,
    amount,
    orderAmount as amount_order,
    shares as count_share,
    probBefore as prob_before,
    probAfter as prob_after,
    limitProb as prob_limit,
    epoch_ms(createdTime) as created_at,
    isFilled as is_filled,
    isCancelled as is_cancelled,
    isRedemption as is_redemption
from {{ source('manifold_raw', 'bets') }}
where isFilled = true
  and isCancelled = false
