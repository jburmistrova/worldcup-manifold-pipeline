# ADR-0007: Small `limit` values silently truncate `/v0/search-markets` results

**Status:** Accepted
**Date:** 2026-07-31

## Context

While checking whether a genuine pre-kickoff calibration analysis was feasible (looking for a kickoff-time field on markets), found that Manifold markets carry a `sportsStartTimestamp` field for sports-integrated markets, a real, precise kickoff time. But it appeared on only 2 of our 389 ingested markets, which seemed too sparse to be believable given how many World Cup matches exist.

Investigated by hypothesis, not assumption, in order:

1. **First hypothesis: the same ranking-instability bug as ADR-0006, causing skips instead of duplicates.** Tested directly. Ran 5 independent full pagination sweeps at the script's original `limit=100`. Every sweep returned an identical 389 markets, 4 sports-linked, zero variance. This **disproved** the instability hypothesis; unstable ranking would show variance between sweeps, and there was none.
2. **Isolated the real variable: `limit` itself.** Held everything else constant and varied only the requested page size: `limit=100` and `limit=200` both returned **zero** sports-linked markets, no matter how many pages were paginated through. `limit=500` returned 104. `limit=1000` returned 621 markets total, 108 sports-linked, in a single call that correctly self-terminated (621 < 1000 signals completeness at that size).

Root cause at Manifold's internal-implementation level isn't confirmed. Possibly a candidate-retrieval-then-filter architecture, possibly result grouping/deduplication that behaves differently at different batch sizes. Worth being honest that the *fix* is verified and effective; the underlying *mechanism* is a documented unknown, not a fully explained one.

This is a **second, distinct bug** in the same `fetch_all()` function ADR-0006 already patched. That fix (dedupe by id, addressing duplicate/over-counted results from ranking ties) was correct and necessary, but incomplete. It addressed over-counting without addressing this separate under-counting problem. The original 63-duplicate finding is still real; it just wasn't the whole story.

## Decision

Changed `limit` from 100 to 1000 (the documented API maximum) in `pull_markets.py`. Kept the offset-pagination loop and id-based dedup as defense-in-depth, in case a search term ever exceeds 1000 results. Re-ran the entire pipeline (ingestion, Spark, dbt) since the market set changed substantially.

## Consequences

**Gained:** a materially more complete dataset: 621 markets vs. 389 (+60%), critically including sports-linked markets with real `sportsStartTimestamp` kickoff data that were previously **100% absent** (0 of 389 had it; 108 of 621 do). This reopens genuine pre-kickoff calibration as a viable stretch-scope analysis, which the earlier, smaller dataset couldn't have supported at all.

**Cost:** a full pipeline re-run (ingestion -> Spark -> dbt), and every row count quoted throughout the existing docs became stale and needed updating.

**Methodological note worth keeping:** the redundant-sweep test that disproved the instability hypothesis wasn't wasted effort even though it "found nothing." Ruling out a plausible-sounding explanation via a direct, isolated test is exactly what prevented shipping the wrong fix (more sweeps, which wouldn't have helped) in place of the real one (a bigger `limit`).
