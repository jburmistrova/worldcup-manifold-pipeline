-- Real, filled, non-cancelled trades only, with nonzero size. Cancelled
-- limit orders and share redemptions are excluded, plus a third category
-- found while building int_market_implied_probability: zero-amount,
-- same-timestamp "bets" that appear at market/answer creation with
-- prob_before == prob_after (no price impact) — a system-generated initial
-- share allocation, not a real trade. All three are business-logic
-- decisions about what counts as a "real" trade, so they belong at the
-- staging layer, tested, not silently baked into ingestion or patched
-- around downstream (see ADR-0005, docs/data_dictionary.md).
select
    id as bet_id,
    contractId as market_id,
    -- present (a real id) on MULTIPLE_CHOICE-market bets, absent (not just
    -- null) on BINARY-market bets — each answer has its own independent
    -- probability track. downstream, always group/partition by
    -- (market_id, answer_id) together, never market_id alone, or bets on
    -- different answers of the same multi-choice market will get mixed
    -- into one nonsensical "probability path"
    answerId as answer_id,
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
  and amount != 0
