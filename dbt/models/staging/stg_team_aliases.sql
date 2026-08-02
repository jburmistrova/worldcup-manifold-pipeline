-- Pure pass-through of the seed (dbt/seeds/team_aliases.csv). Kept as its
-- own staging model, even though there's nothing to rename or type-convert
-- here, so every downstream model references seeds through staging
-- consistently, not some through staging and this one directly.
select
    alias,
    canonical_name
from {{ ref('team_aliases') }}
