-- Polymarket's own "market" is closer to Manifold's "answer" than its
-- "market," for grouped questions specifically: an event like "World Cup
-- Winner" splits into 50+ separate binary markets, one per team, linked by
-- negRiskMarketID, not one multi-choice market the way Manifold's outright
-- winner is (see ADR-0011). Mapped the same way Manifold's own
-- BINARY/MULTIPLE_CHOICE split already works: canonical market_id/answer_id
-- depend on whether this market belongs to a negRisk group. A market with
-- no negRiskMarketID (a genuine standalone binary question) keeps
-- answer_id NULL, exactly like a Manifold BINARY market.
--
-- resolution and prob are derived from outcome_prices (a JSON-encoded
-- array string, e.g. '["1", "0"]' once resolved), Polymarket's equivalent
-- of Manifold's own already-resolved resolution field. A closed market with
-- outcome_prices[0] = '1' resolved YES, '0' resolved NO. Unlike Manifold's
-- single-select MULTIPLE_CHOICE markets (ADR-0008/lessons_learned), no
-- group-level lookup is needed here: each Polymarket market's own
-- outcome_prices already says whether that specific team's market resolved
-- YES or NO, it isn't only recorded once at the group level.
--
-- Gated behind INCLUDE_POLYMARKET (default: off), same reasoning as
-- int_all_market_ticks: a plain `dbt build` builds every model in the
-- project regardless of what references it, so this needs its own
-- disable, not just going unreferenced when the flag is off.
{{ config(enabled = env_var('INCLUDE_POLYMARKET', 'false') == 'true') }}

select
    coalesce(neg_risk_market_id, market_id) as market_id,
    case when neg_risk_market_id is not null then market_id end as answer_id,
    -- the individual Polymarket market's own raw id, distinct from the
    -- canonical market_id above once negRisk grouping applies. Not needed
    -- downstream for grading (condition_id already uniquely identifies
    -- this market for joins), kept for traceability back to the raw data.
    market_id as polymarket_market_id,
    condition_id,
    question,
    groupItemTitle as answer_text,
    'BINARY' as outcome_type,
    case
        when closed and json_extract_string(outcome_prices, '$[0]') = '1' then 'YES'
        when closed and json_extract_string(outcome_prices, '$[1]') = '1' then 'NO'
    end as resolution,
    closed as is_resolved,
    cast(json_extract_string(outcome_prices, '$[0]') as double) as prob,
    volume,
    liquidity as liquidity_total,
    try_cast(created_at as timestamp) as created_at,
    try_cast(closed_time as timestamp) as closed_at,
    try_cast(closed_time as timestamp) as resolved_at,
    json_extract_string(clob_token_ids, '$[0]') as yes_token_id
from {{ source('polymarket_raw', 'polymarket_markets') }}
