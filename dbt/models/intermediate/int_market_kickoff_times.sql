-- Matches Manifold markets/answers to real kickoff times from
-- stg_worldcup_schedule, only where the source text fits one of three
-- strict, unambiguous patterns (see ADR-0008). Anything that doesn't fit
-- gets no match rather than a guessed one. Text similarity or fuzzy NLP matching
-- was deliberately rejected: a market like "Will Norway advance to the
-- quarterfinals?" mentions a team but isn't about one game, and a wrong
-- kickoff time silently attached to it would be worse than an honest gap.
--
-- Three match sources, all confirmed empirically before writing this query,
-- not assumed:
-- 1. Clean-format MULTIPLE_CHOICE markets, e.g. "TUN vs JPN [World Cup '26]".
--    Covers 108 markets in that exact shape, all already carrying
--    sports_start_at from Manifold directly. Used to validate this matcher
--    against a known-good answer (see the model tests).
-- 2. One market phrased differently, full team names instead of codes:
--    "Argentina vs England: FIFA 2026 World Cup". Confirmed this exact
--    pattern matches only this one market, nothing else, before adding it
--    as its own branch rather than loosening branch 1 to catch it.
-- 3. The 102 answers nested inside the 5 "Mega-Market" round-aggregator
--    questions, in the strict shape "{Team A} beats {Team B} <soccer ball>
--    {date} ({time}) {Broadcaster}". Confirmed this pattern matches exactly
--    102 answers total, zero elsewhere, before trusting it as a filter.
--
-- DuckDB-only (regexp_extract/regexp_matches, DuckDB's RE2-based
-- functions): a deliberate scope line, not an oversight. Postgres has its
-- own regex functions with different signatures (regexp_match returns an
-- array, not a matched group directly), and making this genuinely portable
-- across regex dialects isn't the point of the postgres target, which
-- exists for Kubernetes StatefulSet practice (ADR-0004), not full
-- cross-database SQL portability. See that ADR's postgres-target update.
{{ config(enabled = target.type != 'postgres') }}

with clean_format_markets as (

    select
        market_id,
        cast(null as varchar) as answer_id,
        sports_start_at as manifold_kickoff_at,
        upper(regexp_extract(question, '([A-Z]{3})\s+vs\s+.*?([A-Z]{3})', 1)) as raw_team1,
        upper(regexp_extract(question, '([A-Z]{3})\s+vs\s+.*?([A-Z]{3})', 2)) as raw_team2
    from {{ ref('stg_manifold_markets') }}
    where regexp_matches(question, '[A-Z]{3}\s+vs\s+.*[A-Z]{3}.*World Cup')

),

full_name_markets as (

    select
        market_id,
        cast(null as varchar) as answer_id,
        sports_start_at as manifold_kickoff_at,
        regexp_extract(question, '^(.+?) vs (.+?):.*World Cup', 1) as raw_team1,
        regexp_extract(question, '^(.+?) vs (.+?):.*World Cup', 2) as raw_team2
    from {{ ref('stg_manifold_markets') }}
    where regexp_matches(question, '^.+? vs .+?:.*World Cup')

),

mega_market_answers as (

    select
        market_id,
        answer_id,
        cast(null as timestamp) as manifold_kickoff_at,
        regexp_extract(answer_text, '^(.+?) beats (.+?) ⚽', 1) as raw_team1,
        regexp_extract(answer_text, '^(.+?) beats (.+?) ⚽', 2) as raw_team2
    from {{ ref('stg_manifold_market_answers') }}
    where regexp_matches(answer_text, '^.+? beats .+? ⚽')

),

candidates as (
    select * from clean_format_markets
    union all
    select * from full_name_markets
    union all
    select * from mega_market_answers
),

-- resolve whatever spelling/code Manifold used to openfootball's canonical
-- team name. coalesce falls back to the raw value unchanged when no alias
-- row applies (most Mega-Market answers already use the canonical name
-- directly and don't need remapping; only the codes and the 4 real naming
-- mismatches found empirically do).
resolved as (

    select
        c.market_id,
        c.answer_id,
        c.manifold_kickoff_at,
        coalesce(a1.canonical_name, c.raw_team1) as team1,
        coalesce(a2.canonical_name, c.raw_team2) as team2
    from candidates c
    left join {{ ref('stg_team_aliases') }} a1 on c.raw_team1 = a1.alias
    left join {{ ref('stg_team_aliases') }} a2 on c.raw_team2 = a2.alias

)

select
    r.market_id,
    r.answer_id,
    r.manifold_kickoff_at,
    s.kickoff_at as openfootball_kickoff_at,
    s.round,
    s.team1 as schedule_team1,
    s.team2 as schedule_team2
from resolved r
-- unordered pair match: Manifold's phrasing order doesn't always match
-- openfootball's home/away order. Safe because no two teams meet twice in
-- this tournament, confirmed empirically (104 matches, 104 unique pairs).
inner join {{ ref('stg_worldcup_schedule') }} s
    on (s.team1 = r.team1 and s.team2 = r.team2)
    or (s.team1 = r.team2 and s.team2 = r.team1)
