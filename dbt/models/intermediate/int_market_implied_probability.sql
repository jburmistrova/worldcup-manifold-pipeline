-- Reconstructs the probability path per (market_id, answer_id), computes a
-- running volume-weighted average probability, and ranks each trade by how
-- big a repricing jump it caused. Partitioned by (market_id, answer_id)
-- together, not market_id alone. MULTIPLE_CHOICE markets have one
-- independent probability track per answer; mixing them would produce a
-- meaningless probability path. See stg_manifold_bets for why answer_id is
-- null for BINARY markets and how that's handled correctly by this grouping.

with ordered_bets as (

    select
        market_id,
        answer_id,
        bet_id,
        created_at,
        amount,
        prob_before,
        prob_after,
        prob_after - prob_before as prob_change,
        row_number() over (
            partition by market_id, answer_id
            order by created_at
        ) as tick_number
    from {{ ref('stg_manifold_bets') }}

)

select
    market_id,
    answer_id,
    bet_id,
    created_at,
    tick_number,
    amount,
    prob_before,
    prob_after,
    prob_change,

    -- running VWAP: (prob_before + prob_after) / 2 as this trade's effective
    -- price, weighted by abs(amount) as its dollar volume, cumulative up to
    -- and including this tick
    sum(((prob_before + prob_after) / 2) * abs(amount)) over (
        partition by market_id, answer_id
        order by created_at
        rows between unbounded preceding and current row
    ) / sum(abs(amount)) over (
        partition by market_id, answer_id
        order by created_at
        rows between unbounded preceding and current row
    ) as prob_vwap_running,

    -- rank 1 = the single biggest repricing jump for this market/answer
    rank() over (
        partition by market_id, answer_id
        order by abs(prob_change) desc
    ) as jump_rank

from ordered_bets
