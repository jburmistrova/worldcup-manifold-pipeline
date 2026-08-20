-- Port of dbt/models/intermediate/int_market_kickoff_times.sql. Matches
-- Manifold markets/answers to real kickoff times, only where the source
-- text fits one of three strict, unambiguous patterns (ADR-0008). No fuzzy
-- matching -- an unmatched market/answer is absent here, not guessed at.
--
-- Was DuckDB-only on the local pipeline (`enabled = target.type != 'postgres'`)
-- because Postgres's regex functions have a different signature/return
-- shape than DuckDB's. That restriction does NOT carry over to this port:
-- Spark SQL's regexp_extract(str, pattern, idx) has the identical signature
-- to DuckDB's, and rlike is Spark's direct equivalent of DuckDB's
-- regexp_matches boolean check. Verified by actually running this model
-- and comparing its row counts against the known local numbers (108
-- clean-format matches, 102 Mega-Market answers), not assumed compatible
-- from the function names alone. See ADR-0016.
CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.intermediate.int_market_kickoff_times (
  CONSTRAINT market_answer_unique EXPECT (dedup_ok) ON VIOLATION FAIL UPDATE,
  CONSTRAINT openfootball_kickoff_at_not_null EXPECT (openfootball_kickoff_at IS NOT NULL) ON VIOLATION FAIL UPDATE,
  -- port of dbt/tests/assert_kickoff_match_validated_against_known_good.sql
  -- (a singular test there, a row-level expectation here): wherever
  -- Manifold's own sports_start_at already exists, the openfootball-derived
  -- kickoff time must agree exactly. This is the validation gate ADR-0008
  -- requires before trusting the same logic on rows with no independent
  -- ground truth.
  CONSTRAINT kickoff_validated_against_known_good EXPECT (
    answer_id IS NOT NULL OR manifold_kickoff_at IS NULL OR manifold_kickoff_at = openfootball_kickoff_at
  ) ON VIOLATION FAIL UPDATE
)
AS
WITH clean_format_markets AS (
  SELECT
    market_id,
    cast(null AS string) AS answer_id,
    sports_start_at AS manifold_kickoff_at,
    upper(regexp_extract(question, '([A-Z]{3})\\s+vs\\s+.*?([A-Z]{3})', 1)) AS raw_team1,
    upper(regexp_extract(question, '([A-Z]{3})\\s+vs\\s+.*?([A-Z]{3})', 2)) AS raw_team2
  FROM ${catalog}.staging.stg_manifold_markets
  WHERE question rlike '[A-Z]{3}\\s+vs\\s+.*[A-Z]{3}.*World Cup'
),

full_name_markets AS (
  SELECT
    market_id,
    cast(null AS string) AS answer_id,
    sports_start_at AS manifold_kickoff_at,
    regexp_extract(question, '^(.+?) vs (.+?):.*World Cup', 1) AS raw_team1,
    regexp_extract(question, '^(.+?) vs (.+?):.*World Cup', 2) AS raw_team2
  FROM ${catalog}.staging.stg_manifold_markets
  WHERE question rlike '^.+? vs .+?:.*World Cup'
),

mega_market_answers AS (
  SELECT
    market_id,
    answer_id,
    cast(null AS timestamp) AS manifold_kickoff_at,
    regexp_extract(answer_text, '^(.+?) beats (.+?) ⚽', 1) AS raw_team1,
    regexp_extract(answer_text, '^(.+?) beats (.+?) ⚽', 2) AS raw_team2
  FROM ${catalog}.staging.stg_manifold_market_answers
  WHERE answer_text rlike '^.+? beats .+? ⚽'
),

candidates AS (
  SELECT * FROM clean_format_markets
  UNION ALL
  SELECT * FROM full_name_markets
  UNION ALL
  SELECT * FROM mega_market_answers
),

resolved AS (
  SELECT
    c.market_id,
    c.answer_id,
    c.manifold_kickoff_at,
    coalesce(a1.canonical_name, c.raw_team1) AS team1,
    coalesce(a2.canonical_name, c.raw_team2) AS team2
  FROM candidates c
  LEFT JOIN ${catalog}.staging.stg_team_aliases a1 ON c.raw_team1 = a1.alias
  LEFT JOIN ${catalog}.staging.stg_team_aliases a2 ON c.raw_team2 = a2.alias
),

matched AS (
  SELECT
    r.market_id,
    r.answer_id,
    r.manifold_kickoff_at,
    s.kickoff_at AS openfootball_kickoff_at,
    s.round,
    s.team1 AS schedule_team1,
    s.team2 AS schedule_team2
  FROM resolved r
  -- unordered pair match: no two teams meet twice in this tournament
  -- (confirmed empirically in the original build, 104 matches, 104 unique
  -- pairs), so this can't produce more than one match per candidate.
  INNER JOIN ${catalog}.staging.stg_worldcup_schedule s
    ON (s.team1 = r.team1 AND s.team2 = r.team2)
    OR (s.team1 = r.team2 AND s.team2 = r.team1)
)

SELECT
  *,
  COUNT(*) OVER (PARTITION BY market_id, answer_id) = 1 AS dedup_ok
FROM matched
