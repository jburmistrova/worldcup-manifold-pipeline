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
--
-- The market-level-to-answer fan-out this needs (see int_answer_kickoff_times
-- for why it's needed at all) used to live inline here. Extracted once
-- mart_match_price_history needed the identical fan-out, so it isn't
-- maintained in two places. See ADR-0009.

with pre_kickoff_ticks as (

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
    inner join {{ ref('int_answer_kickoff_times') }} k
        on p.market_id = k.market_id
        and p.answer_id = k.answer_id
    where p.created_at <= k.openfootball_kickoff_at

)

select
    market_id,
    answer_id,
    created_at as last_trade_before_kickoff_at,
    prob_after as pre_kickoff_prob
from pre_kickoff_ticks
where recency_rank = 1
