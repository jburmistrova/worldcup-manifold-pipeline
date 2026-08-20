-- Real, executable Unity Catalog grants. This is a single-user Free
-- Edition workspace, so there's no second person to actually restrict --
-- the point of running this for real is to demonstrate the mechanic
-- (catalog/schema-level GRANT, least-privilege by layer) rather than to
-- lock anyone out. `account users` is Unity Catalog's real built-in group
-- for every user in the account, not a placeholder name.
--
-- Layered on purpose, mirroring the medallion-style access pattern this
-- structure is meant to demonstrate: broad read access to the marts
-- consumers actually query, narrower access to raw/staging/intermediate,
-- which exist to be read by the pipeline, not queried ad hoc.

GRANT USE CATALOG ON CATALOG worldcup_manifold TO `account users`;

GRANT USE SCHEMA ON SCHEMA worldcup_manifold.marts TO `account users`;
GRANT SELECT ON SCHEMA worldcup_manifold.marts TO `account users`;

GRANT USE SCHEMA ON SCHEMA worldcup_manifold.staging TO `account users`;
GRANT USE SCHEMA ON SCHEMA worldcup_manifold.intermediate TO `account users`;
GRANT USE SCHEMA ON SCHEMA worldcup_manifold.raw TO `account users`;
-- Deliberately no SELECT grant on raw/staging/intermediate: those layers
-- exist for the pipeline to read/write, not for ad hoc querying, the same
-- "marts are the query surface" boundary a real warehouse would enforce.
