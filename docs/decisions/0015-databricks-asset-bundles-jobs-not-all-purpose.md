# ADR-0015: Databricks Asset Bundles + Jobs, not all-purpose compute or click-built resources

**Status:** Accepted
**Date:** 2026-08-19

## Context

Porting this project's ingestion (`ingest/pull_*.py`) and Spark flatten step (`spark/flatten_to_parquet.py`, `spark/flatten_polymarket.py`) to Databricks needed a real answer to two separate questions: how the ingestion/flatten code gets deployed and run (a notebook clicked together in the UI vs. something version-controlled and deployable), and what compute it runs on (a persistent all-purpose cluster someone stays logged into vs. a Job that runs to completion and stops). Both mirror decisions this project already made once for Kubernetes (ADR-0002, ADR-0003) and are worth making the same way here, not by default.

## Decisions

**Declarative Automation Bundles (DABs, formerly Databricks Asset Bundles), not notebooks clicked together in the workspace UI.** `databricks/databricks.yml` + `databricks/resources/*.yml` define the ingestion Job and the DLT pipeline (ADR-0016) as code, deployed with `databricks bundle deploy` and run with `databricks bundle run`, the same "infrastructure as code, not manual setup" standard `k8s/*.yaml` and `dbt/` already hold this project to. A notebook built by hand in the UI has no diff, no code review, and nothing to reproduce from a clean workspace; a bundle does.

**A Databricks Job (`worldcup_ingest_and_flatten`), not an all-purpose (interactive) cluster.** Direct parallel to ADR-0003's Kubernetes Job-not-CronJob-or-Deployment reasoning: ingestion is something that runs to completion once and stops, not a service to keep up or something anyone needs to stay interactively attached to. A Job also gets retry semantics (`max_retries`, though not configured here beyond the ingestion scripts' own `retry_get.py` backoff) and a clean, inspectable run history (`databricks jobs get-run`) instead of scrollback in a notebook someone happened to leave open.

**Serverless compute on every task (no `new_cluster`/`job_clusters` block), not a classic job cluster.** This workspace's own Free Edition setup already pointed here before this ADR was written: Phase 0 found a pre-provisioned "Serverless Starter Warehouse" and zero running classic clusters, and `clusters list-node-types` succeeding doesn't by itself mean classic cluster creation is the intended path on this tier. Omitting cluster config on a `notebook_task` is Databricks' own documented way to get serverless; verified for real, not assumed, by actually running the ingestion job this way, see below.

## What actually happened running it

**A real bug, not a hypothetical one, caught on the first two run attempts.** Both ingestion notebooks originally used `os.environ["MAX_RETRIES"] = ...` in the widget-parsing cell before `import os` ran in a later cell -- worked locally in any linear Python script, but a genuine `NameError` here since Databricks notebook cells execute in the order the file defines them, not in some inferred dependency order. Fixed by moving `import os` to the top. Caught by actually submitting the job and reading `databricks jobs get-run-output`'s traceback, not by code review.

**A second, more interesting bug, also only found by actually running it, not by reading the file.** Every `# MAGIC %md ## Step N: ...` markdown cell in both ingestion notebooks was immediately followed by real Python code with no `# COMMAND ----------` separator between them. Databricks' notebook-source format requires every line of a cell whose first line is `# MAGIC` to carry that same prefix; without a new cell boundary, the following un-prefixed code doesn't raise a syntax error, it silently gets swallowed into the markdown cell and never executes. The job ran, printed nothing wrong, and finished in under two minutes (real API pulls of this scale take much longer) -- until the final `dbutils.notebook.exit()` cell referenced a variable (`markets`, `events`) that had genuinely never been assigned, because the entire "Step 1" cell that would have assigned it had been silently absorbed as documentation. A `NameError` at the very last cell was the only visible symptom of code that never ran at all. Fixed by inserting `# COMMAND ----------` before every code block that follows a `%md` block.

## Consequences

**Gained:** a real, reviewable, redeployable definition of the ingestion job (`databricks bundle deploy` reproduces it from a clean workspace), serverless compute that matches what this Free Edition workspace is actually provisioned for, and two real, found-not-assumed bugs specific to porting linear Python scripts into Databricks' notebook-cell execution model -- a genuine "what actually broke the first time" finding, the same category PROJECT_SPEC.md already tracks for the original build.

**Cost:** one token-scope friction found along the way, unrelated to compute choice: the Databricks personal access token generated for this project (deliberately scoped, not "All APIs", per Databricks' own UI recommendation) lacks the `access-management` scope, so a `permissions:` block in a bundle resource file 403s on deploy. Removed rather than re-scoped, since this is a single-user workspace with no one else to grant access to -- a real, deliberate scope boundary of this specific token, not an oversight.

**Not done:** a schedule/trigger on the ingestion Job. World Cup 2026 is over; like the original Kubernetes Job (ADR-0003), this is a one-time backfill, not a live-polling pipeline, so a cron trigger would be a feature this workload doesn't need, not a gap.
