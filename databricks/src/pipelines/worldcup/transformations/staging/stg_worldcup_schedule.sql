-- Port of dbt/models/staging/stg_worldcup_schedule.sql. Same seed
-- (dbt/seeds/worldcup_schedule.csv, openfootball/worldcup.json CC0-1.0, see
-- ADR-0008), copied unmodified into the UC Volume. nullif('') for
-- knockout-stage matches' blank group_name, same correction the dbt
-- original makes at this layer, not left for downstream to handle.
CREATE OR REFRESH MATERIALIZED VIEW stg_worldcup_schedule (
  CONSTRAINT team1_not_null EXPECT (team1 IS NOT NULL) ON VIOLATION FAIL UPDATE,
  CONSTRAINT team2_not_null EXPECT (team2 IS NOT NULL) ON VIOLATION FAIL UPDATE,
  CONSTRAINT kickoff_at_not_null EXPECT (kickoff_at IS NOT NULL) ON VIOLATION FAIL UPDATE
)
AS
SELECT
  round,
  cast(match_date AS date) AS match_date,
  cast(kickoff_at_utc AS timestamp) AS kickoff_at,
  team1,
  team2,
  score_team1,
  score_team2,
  nullif(group_name, '') AS group_name,
  ground
FROM read_files(
  '${raw_volume_path}/seeds/worldcup_schedule.csv',
  format => 'csv',
  header => true,
  schema => 'round STRING, match_date STRING, kickoff_at_utc STRING, team1 STRING, team2 STRING, score_team1 INT, score_team2 INT, group_name STRING, ground STRING'
)
