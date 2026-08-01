-- Real, filled, non-cancelled trades only, with nonzero size. Cancelled
-- limit orders and share redemptions are excluded, plus a third category
-- found while building int_market_implied_probability: zero-amount,
-- same-timestamp "bets" that appear at market/answer creation with
-- prob_before == prob_after (no price impact) — a system-generated initial
-- share allocation, not a real trade. All three are business-logic
-- decisions about what counts as a "real" trade, so they belong at the
-- staging layer, tested, not silently baked into ingestion or patched
-- around downstream (see ADR-0005, docs/data_dictionary.md).
--
-- Incremental, overriding staging's folder-level `view` default (see
-- dbt_project.yml) -- this is the one staging model where that matters: it's
-- the largest raw dataset (1.17M+ rows) and the one most analogous to a real
-- fact table, so it's the one worth actually demonstrating incremental logic
-- on rather than a full-refresh view. On this specific dataset (a finished,
-- one-time tournament backfill) there's no genuinely new data arriving after
-- the first run -- so the honest way to think about this is "the mechanism
-- is real and correct, proven by rerunning it and adding a synthetic new row,
-- not by this project's own data actually growing over time."
--
-- Known limitation of the timestamp-cursor approach, not hidden: if two bets
-- share the exact same created_at as the current max and one hasn't landed
-- in the source yet on a given run, it could be missed on the next
-- incremental run (it's older than the *new* max by then). unique_key
-- guards against re-inserting a duplicate, not against this specific gap --
-- a production version processing genuinely live data would use a small
-- overlap window (e.g. `> max(created_at) - interval 1 minute`) to close it.
-- Skipped here since it'd be unfalsifiable on a static backfill with no real
-- late-arriving data to test it against.
{{
    config(
        materialized='incremental',
        unique_key='bet_id'
    )
}}

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

{% if is_incremental() %}
  and epoch_ms(createdTime) > (select coalesce(max(created_at), timestamp '1900-01-01') from {{ this }})
{% endif %}
