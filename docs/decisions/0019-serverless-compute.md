# ADR-0019: Serverless compute, not classic clusters, for both the ingestion Job and the DLT pipeline

**Status:** Accepted
**Date:** 2026-08-19

## Context

Every piece of compute in this migration -- the ingestion/flatten Job's three notebook tasks, and the DLT pipeline's 19-table SQL run -- needed a real compute answer: a classic cluster (a specific node type, worker count, autoscaling policy someone has to size) or serverless (Databricks manages the actual machines, you just declare "no cluster config" or `serverless: true`). This is exactly the "cluster sizing" question the migration's own task list calls out as something ADRs need to cover with a real decision, not a default nobody thought about.

## What was checked before deciding

Phase 0 found this workspace pre-provisioned with a serverless SQL warehouse ("Serverless Starter Warehouse") and zero running classic clusters, `allow-cluster-create`/`allow-instance-pool-create` entitlements present but nothing actually using them. That's a real signal about what this Free Edition workspace is set up to run, not proof classic compute is unavailable -- `databricks clusters list-node-types` does return a real, populated node-type catalog. Rather than spin up a classic cluster just to test whether Free Edition permits it (real cost, real time, for a question this deployment didn't actually need answered), the decision was made on what this project's compute actually needs to do, then verified by using serverless for real and watching it either work or not.

## Decision

**No cluster configuration anywhere in this bundle** -- no `new_cluster`/`job_clusters` block on any of the ingestion Job's three notebook tasks, `serverless: true` on the DLT pipeline resource. Both are Databricks' own documented way to request serverless, and both were run for real, not just deployed and assumed correct:

- The ingestion Job (`worldcup_ingest_and_flatten`) ran all three notebook tasks -- including `flatten_to_delta.py`, real PySpark work (six DataFrame transforms, `explode()`, explicit casts, `saveAsTable()`) -- on serverless compute, end to end, successfully, pulling and flattening the full live dataset (623 markets, 1,178,095 bets, 6,359 exploded Polymarket markets, 4,378,938 trades, 3,209,795 price points) in one run.
- The DLT pipeline (`worldcup_dlt`) ran all 19 materialized views on serverless SDP compute, reaching `COMPLETED` after two real, informative failures along the way (both genuine SQL/dependency bugs, not compute-provisioning problems -- see ADR-0016).

Neither ever needed a classic cluster fallback. Serverless correctly handled real PySpark DataFrame work, real Spark SQL window functions and joins at real data volume, and the DLT engine's own dependency graph execution, not just toy-scale queries.

## Consequences

**Gained:** zero cluster-sizing decisions to actually make (no worker count, no node type, no autoscaling policy to get wrong or defend in an interview) -- a real, legitimate outcome of this specific workload and this specific workspace tier, not a decision dodged. Also gained real evidence, not just Databricks' own marketing claim, that serverless is capable of the actual work this project needed: both the PySpark flatten step and the DLT pipeline's window-function-heavy SQL (VWAP reconstruction, repricing-jump ranking, regex-based kickoff matching) ran correctly on it.

**Cost:** no control over instance type, no ability to tune for this workload's specific shape (e.g., the `stg_manifold_bets` filter over 1.17M rows might benefit from a differently-sized cluster than the smaller staging tables) -- a real tradeoff serverless makes on this project's behalf. At this dataset's actual scale (the same "practice-scale, not production-scale" honesty ADR-0002 already applies to Spark generally), that tradeoff never mattered in practice.

**Not done:** never tested classic cluster compute at all on this workspace, so this ADR can't say whether Free Edition actually blocks it -- only that serverless worked and nothing here needed the comparison. A genuinely different finding from "classic compute isn't available here," worth keeping distinct.
