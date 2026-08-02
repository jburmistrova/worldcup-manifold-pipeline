# ADR-0002: Use Spark despite data that would fit in pandas

**Status:** Accepted
**Date:** 2026-07-30

## Context

This project's actual data volume (a few hundred World Cup 2026 markets, likely tens of thousands of bets total once trade-level data is pulled) comfortably fits in memory. It would run fine in pandas on a laptop. Spark is not a technical requirement of this workload.

## Decision

Use PySpark anyway, deliberately, to parse and flatten raw bet-tick JSON from the Manifold API at scale into clean, partitioned Parquet.

*Updated by [ADR-0005](0005-elt-not-etl-transformation-lives-in-dbt.md): the probability reconstruction, volume-weighted aggregation, and repricing-jump detection originally described here moved to dbt SQL models, to keep this project's transformation logic in one place (the warehouse) and earn the ELT label rather than just resemble it. Spark's role is now bounded to extract + load. See that ADR for the reasoning.*

## Consequences

**Gained:** hands-on practice with the distributed DataFrame API, partitioning, and Spark SQL, one of three specific, named skill gaps this project exists to close (see `PROJECT_SPEC.md`).

**Gave up / risk:** added complexity not justified by the data volume. This is flagged explicitly here rather than left implicit, because claiming Spark was *necessary* here wouldn't survive a follow-up question. The honest framing, if asked: "this dataset would fit in pandas. I used Spark deliberately to build the distributed-processing pattern on data small enough to debug easily, not because this dataset demanded it."

## When Spark actually makes sense vs. the alternatives

Worth having an actual decision framework ready, not just "Spark is big data tech." That's not a real answer if asked why it wasn't Polars or DuckDB instead. Other engines that also read semi-structured data and write Parquet, all real, current options (Polars specifically is already in production use for exactly this kind of job at companies I know, not a hypothetical):

| Tool | Reach for it when | Not when |
|---|---|---|
| **Spark** | Data doesn't fit in memory on one machine; you need to run across a real multi-node cluster; you need Structured Streaming, MLlib, or mature large-scale shuffle/join optimization; your org already runs a Spark platform (EMR/Databricks/Dataproc/on-prem), so the marginal cost of one more job is near zero. | Data fits comfortably in memory. The JVM startup, Python-JVM serialization overhead (via Py4J), and cluster machinery are pure cost with no benefit at that point. |
| **Polars** | Single-machine, "medium data" (roughly up to low tens of GB) that needs real speed. Rust-backed, genuinely multi-threaded, lazy query optimization in a similar spirit to Spark's Catalyst but with none of the JVM/cluster overhead. Often faster than both pandas *and* Spark at this scale specifically because there's no serialization boundary or cluster coordination cost. | You actually need to scale past one machine, or need Spark-specific ecosystem pieces (streaming, MLlib). |
| **DuckDB** | SQL-first workloads; format conversion (exactly this task, `COPY (SELECT * FROM read_json_auto(...)) TO 'out.parquet'` is one statement); anywhere you're already using SQL-centric tooling downstream (this project uses it for dbt anyway). Embedded, no server, vectorized columnar execution. | Need a general-purpose DataFrame API for complex programmatic transformations, not just SQL-shaped ones. |
| **pandas + pyarrow** | The most broadly known default; fine for genuinely small data; pyarrow is the actual library doing the Parquet I/O underneath, for pandas *and* Spark both. | Performance matters and data is more than "small." Single-threaded by default, more memory-hungry than Polars or DuckDB for the same task. |

**Honest bottom line for this project:** given our actual data volume (a few hundred MB), DuckDB alone could plausibly have replaced this entire Spark step: read the raw JSONL, write Parquet, in one SQL statement, with a tool we're installing anyway for dbt. Spark is here because practicing Spark specifically was the point, not because it was the right engineering call for this data. That's the answer to give if asked directly, not a justification for why Spark was "needed."

## Why have a separate "flatten raw data" step before the warehouse at all, then?

A sharper version of the same question: DuckDB can read JSON Lines natively (`read_json_auto()`), so why not skip this Spark step entirely and let dbt read the raw files directly as a source? For this project, that would work. It's a completely legitimate, arguably leaner architecture at our scale. But the pattern of a separate flatten/load step before the warehouse is real and earns its place at larger companies, for reasons distinct from "data volume":

- **The warehouse often can't read raw files directly at all.** DuckDB is unusually convenient in being able to just point at files on disk. Snowflake, BigQuery, and Redshift generally can't casually query a pile of raw JSON sitting in object storage the way DuckDB can locally. An actual **load** step is needed to get data into the warehouse in queryable form first. Spark (or a managed loader like Fivetran/Airbyte) commonly plays that role, distinct from dbt's transform-only job.
- **Multiple consumers beyond just one warehouse.** In a lakehouse pattern, the clean Parquet/Delta layer often feeds ML training jobs, other services, and ad-hoc analytics directly, not just one dbt project. A shared, general-purpose layer in a data lake is more broadly reusable than data loaded straight into one specific warehouse. This project has exactly one consumer (dbt), so this benefit doesn't apply here.
- **Team/ownership boundaries, not just technical need.** At a lot of companies, a data engineering team owns "get raw data into clean, typed form" (often Spark, on a data lake) and a separate analytics engineering team owns "transform clean data into business answers" (dbt). The Spark -> dbt split is sometimes an organizational handoff point as much as a technical one.

None of these apply to this project: one consumer, no existing Spark platform, one person doing every role. Worth being able to name the real reasons this pattern exists elsewhere, distinct from restating "big data" as if it were the only justification.
