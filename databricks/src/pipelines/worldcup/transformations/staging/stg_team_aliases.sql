-- Port of dbt/models/staging/stg_team_aliases.sql. dbt's seed
-- (dbt/seeds/team_aliases.csv) becomes a static file read here: "Small
-- static file load (reference data, no streaming read) -> Materialized
-- View" per Databricks' own SDP guidance. Same file, copied unmodified
-- into the Unity Catalog Volume (see databricks/uc_setup); read_files, not
-- STREAM read_files -- this is a one-time static lookup table, not an
-- incrementally-arriving source.
CREATE OR REFRESH MATERIALIZED VIEW stg_team_aliases
AS
SELECT
  alias,
  canonical_name
FROM read_files(
  '${raw_volume_path}/seeds/team_aliases.csv',
  format => 'csv',
  header => true,
  schema => 'alias STRING, canonical_name STRING'
)
