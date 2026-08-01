-- One row per resolved prediction — either a BINARY market or one answer of
-- a MULTIPLE_CHOICE market — with its resolution-time predicted probability
-- and actual outcome. This is the calibration/favorite-longshot-bias mart:
-- bucket by prob_bucket, compare predicted probability to actual YES rate.
--
-- Built from the staging tables directly, not int_market_implied_probability
-- — calibration is a point-in-time comparison (probability at resolution vs.
-- actual outcome), and stg_manifold_markets/stg_manifold_market_answers
-- already carry Manifold's own resolution-time probability snapshot. The
-- reconstructed probability *path* belongs to the stretch marts instead.
--
-- BINARY and MULTIPLE_CHOICE are two different staging tables with
-- different column names for the same underlying concept (a resolved
-- yes/no prediction) — unioned here into one consistent shape.

with binary_predictions as (

    select
        market_id,
        cast(null as varchar) as answer_id,
        question as label,
        prob as predicted_prob,
        resolution = 'YES' as is_yes,
        volume,
        liquidity_total
    from {{ ref('stg_manifold_markets') }}
    where outcome_type = 'BINARY'
      and resolution in ('YES', 'NO')

),

multiple_choice_predictions as (

    select
        market_id,
        answer_id,
        answer_text as label,
        prob_resolution as predicted_prob,
        resolution = 'YES' as is_yes,
        volume,
        liquidity_total
    from {{ ref('stg_manifold_market_answers') }}
    where resolution in ('YES', 'NO')

),

unioned as (
    select * from binary_predictions
    union all
    select * from multiple_choice_predictions
)

select
    market_id,
    answer_id,
    label,
    predicted_prob,
    is_yes,
    volume,
    liquidity_total,
    -- decile buckets (0.0-0.1, 0.1-0.2, ... 0.9-1.0), matching how
    -- Manifold's own published platform-wide calibration is bucketed, for
    -- a like-for-like comparison rather than an arbitrary bucket width.
    -- Shared macro (macros/prob_bucket.sql) -- mart_trade_calibration needs
    -- the exact same rule applied to a different expression.
    {{ prob_bucket('predicted_prob') }} as prob_bucket

from unioned
