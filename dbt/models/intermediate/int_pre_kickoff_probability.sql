-- For each market/answer with a validated kickoff time
-- (int_market_kickoff_times), finds the market's implied probability from
-- its LAST real trade strictly before kickoff: the actual "what did the
-- market believe right before the game started" value the original problem
-- statement asks for (see docs/architecture.md), not the resolution-time
-- snapshot mart_market_efficiency uses. Uses prob_after (the instantaneous
-- probability right after that last trade), not a running VWAP average,
-- since the question is what the market believed at that moment, not its
-- average belief across its whole trading history up to that point.
--
-- Markets/answers with zero trades before kickoff (all activity happened
-- after kickoff, e.g. live in-play betting) are correctly absent here, not
-- guessed at.

with market_level_kickoffs as (

    -- kickoff times attached at the market level (the clean-format
    -- "TUN vs JPN" markets) apply to EVERY answer under that market, not
    -- literally to a row where answer_id is NULL. These are
    -- MULTIPLE_CHOICE markets, and every real bet on a MULTIPLE_CHOICE
    -- market carries a real, non-null answer_id (see stg_manifold_bets) --
    -- there's no such thing as an answer_id-is-NULL trade to match against
    -- here, so this has to fan the market-level kickoff time out to each
    -- of that market's real answers instead.
    select
        k.market_id,
        p.answer_id,
        k.openfootball_kickoff_at
    from {{ ref('int_market_kickoff_times') }} k
    inner join (
        select distinct market_id, answer_id
        from {{ ref('int_market_implied_probability') }}
    ) p
        on k.market_id = p.market_id
    where k.answer_id is null

),

answer_level_kickoffs as (

    -- the 102 Mega-Market answers already carry their own specific
    -- answer_id in int_market_kickoff_times, no fan-out needed
    select market_id, answer_id, openfootball_kickoff_at
    from {{ ref('int_market_kickoff_times') }}
    where answer_id is not null

),

all_kickoffs as (
    select * from market_level_kickoffs
    union all
    select * from answer_level_kickoffs
),

pre_kickoff_ticks as (

    select
        p.market_id,
        p.answer_id,
        p.created_at,
        p.prob_after,
        row_number() over (
            partition by p.market_id, p.answer_id
            order by p.created_at desc
        ) as recency_rank
    from {{ ref('int_market_implied_probability') }} p
    inner join all_kickoffs k
        on p.market_id = k.market_id
        and p.answer_id is not distinct from k.answer_id
    where p.created_at <= k.openfootball_kickoff_at

)

select
    market_id,
    answer_id,
    created_at as last_trade_before_kickoff_at,
    prob_after as pre_kickoff_prob
from pre_kickoff_ticks
where recency_rank = 1
