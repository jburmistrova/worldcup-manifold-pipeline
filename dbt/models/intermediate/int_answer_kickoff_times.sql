-- Fans int_market_kickoff_times' market-level kickoff times out to every
-- real answer_id under that market, so every consumer joins against a real
-- (market_id, answer_id) pair instead of re-deriving this fan-out itself.
-- Market-level kickoff times come from the clean-format "TUN vs JPN"-style
-- MULTIPLE_CHOICE markets (see ADR-0008): the kickoff time describes the
-- whole match, which applies to every one of that market's real answers,
-- not literally to a row where answer_id is NULL. Every real bet on a
-- MULTIPLE_CHOICE market carries a real, non-null answer_id (see
-- stg_manifold_bets), so there's no such thing as an answer_id-is-NULL
-- trade to match a NULL-answer_id kickoff time against.
--
-- Extracted out of int_pre_kickoff_probability once a second consumer
-- (mart_match_price_history) needed the exact same fan-out. See ADR-0009.
--
-- Disabled on postgres: depends on int_market_kickoff_times, which is
-- DuckDB-only (see that model). Nothing here has its own dialect-specific
-- SQL, this follows the upstream scope line, not a separate one.
{{ config(enabled = target.type != 'postgres') }}

with market_level_kickoffs as (

    select
        k.market_id,
        p.answer_id,
        k.openfootball_kickoff_at,
        k.round,
        k.schedule_team1,
        k.schedule_team2
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
    select
        market_id,
        answer_id,
        openfootball_kickoff_at,
        round,
        schedule_team1,
        schedule_team2
    from {{ ref('int_market_kickoff_times') }}
    where answer_id is not null

)

select * from market_level_kickoffs
union all
select * from answer_level_kickoffs
