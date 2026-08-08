-- Real-money (Polymarket) vs. play-money (Manifold) calibration comparison,
-- one row per team's outright-winner prediction on each platform, deliberately
-- scoped to just the two platforms' outright World Cup winner markets, not
-- the full dataset (see ADR-0013): a real, comparable event on both sides
-- with unambiguous ground truth, not a full second kickoff-time-matching
-- project for Polymarket's thousands of other, mostly clean-single-match-free
-- markets.
--
-- predicted_prob is each team's last real implied probability strictly
-- before the tournament itself started (2026-06-11 19:00 UTC, the actual
-- first real match kickoff, confirmed against stg_worldcup_schedule), not
-- resolution-time. docs/results.md's own Question 1 finding already showed
-- resolution-time Brier scores are close to meaningless (~0.0008): by
-- resolution the market already knows the outcome, so a resolution-time
-- comparison would mostly measure how fast each platform's price
-- mechanically converges after the answer is public, not genuine belief
-- under real uncertainty, which is the actual question here.
--
-- is_yes: Manifold's outright market never sets a per-answer resolution
-- field (see mart_outright_odds_over_time, lessons_learned.md), so its
-- winner is derived from the market's own resolution field instead.
-- Polymarket's per-market resolution (stg_polymarket_markets) is already
-- correctly self-contained per team, confirmed empirically: 59 NO, 1 YES
-- (Spain), no equivalent derivation needed on that side.
--
-- Gated behind INCLUDE_POLYMARKET (default: off); see int_all_market_ticks.
-- This mart has no meaning at all without Polymarket data, unlike the
-- staging models it depends on, so it's disabled together with them, not
-- separately reconsidered.

{{ config(enabled = env_var('INCLUDE_POLYMARKET', 'false') == 'true') }}

{% set tournament_start = "'2026-06-11 19:00:00'" %}
{% set manifold_outright_market_id = "JRzL2QcArhM674YSO4d8" %}
{% set polymarket_outright_market_id = "0xb5c32a9acd39848acad4913ac4cd49c5de2afcc9d23a8a7ba2419375fab87400" %}

with manifold_pre_tournament_ticks as (

    select
        market_id,
        answer_id,
        prob_after,
        row_number() over (
            partition by market_id, answer_id
            order by created_at desc
        ) as recency_rank
    from {{ ref('int_market_implied_probability') }}
    where market_id = '{{ manifold_outright_market_id }}'
      and created_at < timestamp {{ tournament_start }}

),

manifold_outcomes as (

    select
        a.market_id,
        a.answer_id,
        a.answer_text as team,
        a.answer_id = m.resolution as is_yes
    from {{ ref('stg_manifold_market_answers') }} a
    inner join {{ ref('stg_manifold_markets') }} m
        on a.market_id = m.market_id
    where a.market_id = '{{ manifold_outright_market_id }}'

),

polymarket_pre_tournament_ticks as (

    select
        market_id,
        answer_id,
        prob_after,
        row_number() over (
            partition by market_id, answer_id
            order by created_at desc
        ) as recency_rank
    from {{ ref('int_market_implied_probability') }}
    where market_id = '{{ polymarket_outright_market_id }}'
      and created_at < timestamp {{ tournament_start }}

),

polymarket_outcomes as (

    select
        market_id,
        answer_id,
        answer_text as team,
        resolution = 'YES' as is_yes
    from {{ ref('stg_polymarket_markets') }}
    where market_id = '{{ polymarket_outright_market_id }}'
      and resolution in ('YES', 'NO')

),

manifold_rows as (

    select
        'manifold' as source_platform,
        o.team,
        t.prob_after as predicted_prob,
        o.is_yes
    from manifold_pre_tournament_ticks t
    inner join manifold_outcomes o
        on t.market_id = o.market_id and t.answer_id = o.answer_id
    where t.recency_rank = 1

),

polymarket_rows as (

    select
        'polymarket' as source_platform,
        o.team,
        t.prob_after as predicted_prob,
        o.is_yes
    from polymarket_pre_tournament_ticks t
    inner join polymarket_outcomes o
        on t.market_id = o.market_id and t.answer_id = o.answer_id
    where t.recency_rank = 1

)

select * from manifold_rows
union all
select * from polymarket_rows
