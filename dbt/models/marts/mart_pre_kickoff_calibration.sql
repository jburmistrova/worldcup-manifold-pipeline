-- The genuine pre-kickoff version of mart_market_efficiency's calibration
-- comparison, for the subset of predictions where a validated kickoff time
-- exists (int_market_kickoff_times, see ADR-0008). mart_market_efficiency
-- uses resolution-time probability for all 2,831 predictions since
-- pre-kickoff data wasn't available at full-dataset scale (ADR-0007); this
-- mart answers the original problem statement's actual question, "what did
-- the market believe right before the game started," for the markets/
-- answers where that's now knowable, not a replacement for the larger
-- resolution-time result, an addition alongside it.
--
-- Unlike mart_market_efficiency, there's no BINARY branch here: every
-- validated kickoff time comes from a MULTIPLE_CHOICE market or answer
-- (confirmed empirically in ADR-0008, no BINARY market carries a kickoff
-- time at all), so predictions here are always graded at the answer level.
--
-- Markets/answers with no pre-kickoff trade, or no validated kickoff time
-- at all, are correctly absent (inner join), not guessed at.
--
-- is_yes uses the same derivation as mart_market_efficiency, not a plain
-- a.resolution = 'YES' check: every clean-format/full-name World Cup market
-- here is a "single-select" MULTIPLE_CHOICE market, where Manifold resolves
-- the market itself to the winning answer_id and never sets a.resolution at
-- all (see lessons_learned.md). Checking a.resolution directly would have
-- silently dropped all of them.
--
-- Disabled on postgres: depends (via int_pre_kickoff_probability) on
-- int_market_kickoff_times, which is DuckDB-only (see that model).
{{ config(enabled = target.type != 'postgres') }}

select
    a.market_id,
    a.answer_id,
    a.answer_text as label,
    p.pre_kickoff_prob as predicted_prob,
    case
        when m.resolution = 'MKT' then a.resolution = 'YES'
        else a.answer_id = m.resolution
    end as is_yes,
    a.volume,
    a.liquidity_total,
    -- same shared macro and decile convention as mart_market_efficiency,
    -- for a genuinely like-for-like comparison between the two marts
    {{ prob_bucket('p.pre_kickoff_prob') }} as prob_bucket
from {{ ref('stg_manifold_market_answers') }} a
inner join {{ ref('stg_manifold_markets') }} m
    on a.market_id = m.market_id
inner join {{ ref('int_pre_kickoff_probability') }} p
    on a.market_id = p.market_id
    and a.answer_id = p.answer_id
where
    (m.resolution = 'MKT' and a.resolution in ('YES', 'NO'))
    or (
        m.resolution not in ('CANCEL', 'MKT', 'CHOOSE_MULTIPLE')
        and exists (
            select 1 from {{ ref('stg_manifold_market_answers') }} a2
            where a2.market_id = m.market_id and a2.answer_id = m.resolution
        )
    )
