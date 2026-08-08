-- Unions every platform's price-reconstruction-worthy events into one
-- canonical shape, so int_market_implied_probability's actual
-- reconstruction logic (VWAP, repricing-jump detection) doesn't need to
-- know which platform a row came from.
--
-- Manifold contributes its own real bet-level prob_before/prob_after pairs,
-- unchanged. Briefly considered LAG-deriving these for both platforms
-- uniformly (a single shared derivation, less code), abandoned once real
-- data showed 33-37% of Manifold's MULTIPLE_CHOICE ticks don't satisfy
-- "this trade's before equals the previous trade's after": a real
-- consequence of cpmm-multi-1's shared liquidity pool across a market's
-- answers, not something LAG on one answer's own history alone can see
-- (see lessons_learned.md). Manifold's own reported before/after already
-- reflects the true AMM state; discarding it in favor of a same-answer-only
-- reconstruction would have been a real accuracy regression, not a
-- simplification.
--
-- Polymarket contributes hourly price samples instead, with
-- prob_before/prob_after derived via LAG per (market, answer): validated
-- empirically as sound for Polymarket specifically, no equivalent
-- cross-answer coupling found in 10,000 real trades checked (median
-- trade-to-trade jump ~0.001, nothing like Manifold's up-to-0.96
-- mismatches), each Polymarket outcome is its own independent CLOB order
-- book, not a shared pool (see ADR-0011).
--
-- amount is NULL for every Polymarket row: a price sample has no size,
-- unlike an executed trade. int_market_implied_probability's VWAP
-- weighting has nothing real to weight by for these rows; standard SQL's
-- NULL handling in SUM() correctly leaves prob_vwap_running NULL for
-- Polymarket rather than needing a special case here or a fabricated
-- equal weight.
--
-- Still called bet_id here, even for Polymarket rows: renaming it would
-- ripple through every downstream mart, contract, and test that already
-- depends on this exact column name for Manifold. Not literally a bet for
-- Polymarket's rows, an interface-stability tradeoff, not a claim about
-- what the id represents.
--
-- The Polymarket half is gated behind INCLUDE_POLYMARKET (default: off),
-- not a hard dependency. Once Manifold's own core marts started reading
-- through this union instead of stg_manifold_bets directly, a plain
-- `dbt build` broke outright the moment Polymarket's raw Parquet wasn't
-- present, a real regression against every existing consumer of this
-- pipeline, caught by actually running a Manifold-only build rather than
-- assumed to still work. Polymarket ingestion (ingest/pull_polymarket_*.py,
-- spark/flatten_polymarket.py) is a real, separate, hours-long step; it
-- shouldn't be a silent prerequisite for the pipeline this project was
-- built around in the first place.

with manifold_ticks as (

    select
        market_id,
        answer_id,
        bet_id,
        created_at,
        amount,
        prob_before,
        prob_after,
        'manifold' as source_platform
    from {{ ref('stg_manifold_bets') }}

)

{% if env_var('INCLUDE_POLYMARKET', 'false') == 'true' %}
,
polymarket_ticks as (

    select
        m.market_id,
        m.answer_id,
        -- includes market_id/answer_id, not just a bare row_number(): a
        -- first version used only 'pm-' + row_number(), which resets to 1
        -- for every partition, so "pm-1" collided across all 60 different
        -- Polymarket markets, caught by the model's own uniqueness test
        -- (8,882 real duplicates on the first build) rather than assumed
        -- safe. bet_id is expected to be globally unique on its own,
        -- matching Manifold's real bet IDs, which already are, regardless
        -- of market, so the fix has to make Polymarket's synthesized ones
        -- the same way, not add a compound key downstream only had to
        -- work around.
        'pm-' || m.market_id || '-' || coalesce(m.answer_id, 'x') || '-'
            || cast(row_number() over (partition by m.market_id, m.answer_id order by p.created_at) as varchar) as bet_id,
        p.created_at,
        cast(null as double) as amount,
        lag(p.price) over (partition by m.market_id, m.answer_id order by p.created_at) as prob_before,
        p.price as prob_after,
        'polymarket' as source_platform
    from {{ ref('stg_polymarket_prices') }} p
    inner join {{ ref('stg_polymarket_markets') }} m
        on p.condition_id = m.condition_id

)
{% endif %}

select * from manifold_ticks
{% if env_var('INCLUDE_POLYMARKET', 'false') == 'true' %}
union all
select * from polymarket_ticks
{% endif %}
