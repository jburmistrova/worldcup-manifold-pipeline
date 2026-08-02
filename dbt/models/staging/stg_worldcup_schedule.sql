-- Pure rename + type conversion of the seed (dbt/seeds/worldcup_schedule.csv),
-- no filtering, no rows dropped, same convention as every other staging
-- model. Source: openfootball/worldcup.json (CC0-1.0, verified via GitHub's
-- own license API and the actual LICENSE.md, see ADR-0008).
select
    round,
    cast(match_date as date) as match_date,
    cast(kickoff_at_utc as timestamp) as kickoff_at,
    team1,
    team2,
    score_team1,
    score_team2,
    -- the seed writes '' for knockout-stage matches (no group), not a real
    -- NULL marker, since it's a CSV. Correcting that here, not downstream.
    nullif(group_name, '') as group_name,
    ground
from {{ ref('worldcup_schedule') }}
