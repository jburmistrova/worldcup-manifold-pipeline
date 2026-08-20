# Unity Catalog structure

The governance piece of this migration -- catalog/schema design, access controls, and lineage, all real and applied against the live workspace, not just written as SQL and left unrun. See [ADR-0017](../../docs/decisions/0017-unity-catalog-schema-design.md) for the full reasoning; this doc is the reference, not the argument.

## Catalog and schemas

One catalog, `worldcup_manifold`, created via the SQL Statement Execution API against this workspace's serverless SQL warehouse (`databricks catalogs create` itself 403s on Free Edition's default storage setup -- a real finding, see ADR-0018 and `uc_setup/create_catalog_schema.sql`'s own comment).

| Schema | Contents | Populated by |
|---|---|---|
| `raw` | Landed JSON (Unity Catalog Volume `landed_json`) + bronze Delta tables (`markets`, `market_answers`, `bets`, `polymarket_markets`, `polymarket_trades`, `polymarket_prices`) | `ingest_manifold.py`, `ingest_polymarket.py`, `flatten_to_delta.py` (the ingestion Job) |
| `staging` | 8 tables, pure rename/type per platform, mirrors `dbt/models/staging` | the DLT pipeline (default publish target) |
| `intermediate` | 5 tables, cross-platform reconstruction (VWAP, repricing, kickoff matching), mirrors `dbt/models/intermediate` | the DLT pipeline |
| `marts` | 6 tables, the calibration/efficiency/outright-odds marts, mirrors `dbt/models/marts` | the DLT pipeline |

Verified structure (not just what was intended to be created):

```
$ databricks schemas list worldcup_manifold
default | information_schema | intermediate | marts | raw | staging
```

## Grants

Applied for real via the SQL warehouse (`uc_setup/grants.sql`), then verified with `SHOW GRANTS`, not assumed to have taken effect just because the `GRANT` statements returned `SUCCEEDED`:

```
$ SHOW GRANTS ON SCHEMA worldcup_manifold.marts
Principal        ActionType    ObjectType    ObjectKey
account users    SELECT        SCHEMA        worldcup_manifold.marts
account users    USE SCHEMA    SCHEMA        worldcup_manifold.marts
```

`marts` gets `USE SCHEMA` + `SELECT` (the real query surface). `raw`/`staging`/`intermediate` get `USE SCHEMA` only, no `SELECT` -- those layers exist for the pipeline to read/write, not for ad hoc querying. This is a single-user Free Edition workspace, so `account users` (Unity Catalog's real built-in group for every account user, not a placeholder) is the only principal there is to grant to today; the point of applying this for real is the mechanic, not restricting a second person who doesn't exist yet.

## Lineage

Pulled for real from Unity Catalog's Lineage Tracking API (`/api/2.0/lineage-tracking/table-lineage`) after the DLT pipeline reached `COMPLETED`, not written from what the lineage graph should theoretically look like.

**A real finding along the way:** the `system.access.table_lineage` system table -- the more commonly documented way to query lineage -- isn't usable on this workspace. `databricks system-schemas list` shows the `access` schema in state `MANAGED`, and `databricks system-schemas enable ... access` fails with `"access system schema can only be enabled by Databricks"` -- a Free Edition (or account-tier) restriction, not something fixable from this workspace's own admin settings. The Lineage Tracking API worked instead, and is what the edges below are pulled from.

**Full real chain, one mart traced back to raw, four layers deep:**

```
worldcup_manifold.raw.bets
  -> worldcup_manifold.staging.stg_manifold_bets
    -> worldcup_manifold.intermediate.int_all_market_ticks
      -> worldcup_manifold.intermediate.int_market_implied_probability
        -> worldcup_manifold.intermediate.int_pre_kickoff_probability
          -> worldcup_manifold.marts.mart_pre_kickoff_calibration
```

`stg_manifold_bets` also fans out to a second, independent downstream table confirmed via the same API (`downstreams`, not `upstreams`):

```
worldcup_manifold.staging.stg_manifold_bets
  -> worldcup_manifold.marts.mart_trade_calibration   (direct, bypassing intermediate)
  -> worldcup_manifold.intermediate.int_all_market_ticks
```

`mart_market_efficiency`'s own upstream (the layer boundary the applied grants above are built around) confirms staging is the only layer it reads from directly, no intermediate skip:

```
worldcup_manifold.marts.mart_market_efficiency
  <- worldcup_manifold.staging.stg_manifold_markets
  <- worldcup_manifold.staging.stg_manifold_market_answers
```

This is real, queryable governance metadata now, not a diagram drawn from the SQL by hand -- exactly the artifact the target job descriptions ask about.
