-- One row per real trade on a resolved BINARY market with >= 15 distinct
-- traders, built specifically to replicate Manifold's own published
-- calibration methodology (manifold.markets/calibration) so the Brier score
-- comparison in docs/results.md is apples-to-apples rather than comparing
-- two different things that happen to both be called "Brier score."
--
-- Manifold's own methodology, quoted from their calibration page: "Every
-- hour we sample 2% of all past trades on resolved binary questions with 15
-- or more traders," using "the average probability between the start and
-- end" of each trade as that trade's prediction. mart_market_efficiency
-- doesn't match this: it's one row per market at resolution-time (a single
-- snapshot), includes MULTIPLE_CHOICE answers Manifold's number excludes,
-- and has no trader-count floor. This mart fixes all three.
--
-- We use every qualifying trade rather than a 2% sample. Manifold subsamples
-- for computational cost, recomputing this hourly across their entire
-- platform's trade history -- a performance tradeoff that doesn't apply
-- here at this dataset's scale. Using the full population is strictly more
-- precise, not a deviation from the method's intent.

with binary_markets as (

    select
        market_id,
        resolution = 'YES' as is_yes
    from {{ ref('stg_manifold_markets') }}
    where outcome_type = 'BINARY'
      and resolution in ('YES', 'NO')

),

trader_counts as (

    select
        market_id,
        count(distinct user_id) as trader_count
    from {{ ref('stg_manifold_bets') }}
    where answer_id is null
    group by 1

),

qualifying_markets as (

    select
        bm.market_id,
        bm.is_yes
    from binary_markets bm
    inner join trader_counts tc on bm.market_id = tc.market_id
    where tc.trader_count >= 15

)

select
    b.bet_id,
    b.market_id,
    qm.is_yes,
    (b.prob_before + b.prob_after) / 2 as prob_trade,
    least(floor(((b.prob_before + b.prob_after) / 2) * 10) / 10, 0.9) as prob_bucket
from {{ ref('stg_manifold_bets') }} b
inner join qualifying_markets qm on b.market_id = qm.market_id
where b.answer_id is null
