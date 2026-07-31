# ADR-0001: Data source — Manifold Markets, not Kalshi

**Status:** Accepted
**Date:** 2026-07-30

## Context

The project was originally scoped around Kalshi's public API (see `PROJECT_SPEC.md`'s original framing: a CFTC-regulated, real-money exchange). Before writing any ingestion code, I read Kalshi's actual governing documents rather than assuming "public API" meant "free to use for this."

Two documents apply, and both are more restrictive than expected:

- The **Kalshi Developer Agreement** (accepted on generating an API key) — Section 3: *"Use of Kalshi APIs is expressly limited to facilitating a member's own trading on the Exchange; all other usages are disallowed."* Section 3.1 explicitly prohibits "collecting, caching, aggregating, or storing data or content accessed via the API except for purposes of facilitating your own trading," and separately bars sharing such data with third parties without written authorization.
- The **Kalshi Data Terms of Use** (covering the no-auth public market-data endpoints too, not just the authenticated trading API) — similarly prohibits downloading, storing, and compiling Kalshi Data into a database without prior written consent, and treats "development of any software program" using the data as outside permitted non-commercial use.

Neither carve-out fits a project whose entire point is to ingest, store, and publish an analysis pipeline on GitHub.

## Decision

Switched the data source to **Manifold Markets**. Its Terms of Service (`docs.manifold.markets/terms`, `docs.manifold.markets/data`) explicitly permit building tools against the public API and using data for "academic research, personal projects, and non-commercial use" — only commercial resale or AI/ML model training require a separate paid license. Nothing blocks posting the resulting code or analysis publicly.

## Consequences

**Gained:** a data source whose terms actually fit what this project does, confirmed by reading the primary documents rather than assuming.

**Gave up:** the "CFTC-regulated, real financial stakes" framing. Manifold trades in Mana, a virtual play-money currency, not real financial risk — the resume language changed from "Kalshi's regulated exchange" to a more generic "public prediction-market API" to stay accurate.

**Kept:** genuine, substantial trading activity on real World Cup 2026 markets (some individual markets with $1M+ historical volume), and the full architecture (Spark/dbt/Kubernetes) unchanged — only the ingestion source changed.
