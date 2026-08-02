-- Win-probability movement through each real single-match market/answer
-- (see ADR-0008 for how "real single match" is determined: strict text
-- patterns only, validated against Manifold's own known-good kickoff
-- times, never a guess). One row per real trade.
--
-- This mart does no new reconstruction. int_market_implied_probability
-- already computes the running VWAP and repricing-jump rank for every
-- market/answer; the only job here is scoping that down to genuine
-- matches (via int_answer_kickoff_times, the same validated set
-- mart_pre_kickoff_calibration uses) and attaching team names and kickoff
-- time so the price path is readable without a separate join.
--
-- Disabled on postgres: depends on int_answer_kickoff_times, which
-- depends on int_market_kickoff_times, which is DuckDB-only (see that
-- model).
{{ config(enabled = target.type != 'postgres') }}

select
    p.market_id,
    p.answer_id,
    k.schedule_team1,
    k.schedule_team2,
    k.round,
    k.openfootball_kickoff_at,
    p.bet_id,
    p.created_at,
    p.tick_number,
    p.prob_before,
    p.prob_after,
    p.prob_vwap_running,
    p.jump_rank
from {{ ref('int_market_implied_probability') }} p
inner join {{ ref('int_answer_kickoff_times') }} k
    on p.market_id = k.market_id
    and p.answer_id = k.answer_id
