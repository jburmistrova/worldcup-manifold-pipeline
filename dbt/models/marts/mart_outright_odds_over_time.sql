-- How the tournament-winner "outright" contract repriced over the course
-- of the tournament, one row per real trade on each country's answer.
--
-- Manifold has around 15 separate "who will win the World Cup"-style
-- markets, near-duplicates almost certainly created by different users,
-- not one canonical outright market. Picked the one with real trading
-- activity behind it, checked empirically rather than assumed: $1.65M
-- volume and 18,293 real bets across 50 country answers, an order of
-- magnitude above the next-highest candidate ($150K, 4,076 bets). Not a
-- close call. See ADR-0009.
--
-- is_winner uses the same single-select-resolution derivation as
-- mart_market_efficiency: this market's own resolution field holds the
-- winning answer_id directly, Manifold never sets a per-answer resolution
-- for this market shape. See lessons_learned.md.

{% set outright_market_id = "JRzL2QcArhM674YSO4d8" %}

select
    p.market_id,
    p.answer_id,
    a.answer_text as team,
    p.answer_id = m.resolution as is_winner,
    p.bet_id,
    p.created_at,
    p.tick_number,
    p.prob_before,
    p.prob_after,
    p.prob_vwap_running,
    p.jump_rank
from {{ ref('int_market_implied_probability') }} p
inner join {{ ref('stg_manifold_market_answers') }} a
    on p.market_id = a.market_id
    and p.answer_id = a.answer_id
inner join {{ ref('stg_manifold_markets') }} m
    on p.market_id = m.market_id
where p.market_id = '{{ outright_market_id }}'
