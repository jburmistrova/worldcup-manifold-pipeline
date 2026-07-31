# ADR-0006: Raw layer — JSON Lines, immutable, full API payloads (not CSV)

**Status:** Accepted
**Date:** 2026-07-30

## Context

Three separate problems surfaced together while building the Spark load step, and they compound into one real lesson.

**1. A genuine duplicate-row bug**, root-caused properly: `/v0/search-markets`'s offset-based pagination isn't guaranteed stable across requests (ties in relevance ranking can reorder results between page fetches), so `pull_markets.py` fetched the same market twice for 63 of 451 markets. Confirmed the duplicates were byte-identical. Because `pull_market_answers.py` and `pull_bets.py` both iterate over the market list to know what to fetch, the duplication cascaded downstream (128 duplicate answers, 5,391 duplicate bets) even though neither of those scripts had a bug of its own.

**2. The fix was applied incorrectly.** The duplicate rows were removed by deduplicating and overwriting the raw CSV files **in place**. That violates raw/bronze-layer immutability — the principle that a raw landing layer should be kept exactly as received, unaltered, specifically so there's always a trustworthy, unmodified copy to fall back to or audit against [11: Databricks, *Medallion architecture* — "Bronze Layer: ...No data cleanup or validation is performed here"]. The original CSVs, duplicates and all, are now unrecoverable — overwritten, not just moved. This is a real, named cost of the mistake, not something to gloss over.

**3. Two CSV-parsing bugs, both inherent to the format, not incidental.** Building the Spark reader surfaced: (a) an answer's `text` field containing a nested quoted phrase (`"Shocking decision, Ref!": ...`) that Spark's CSV parser mis-split at an internal comma, shifting every subsequent column by one for that row; (b) three markets with a literal newline inside their `question` field, which Spark's default (non-`multiLine`) CSV reader split into two physical rows each. Both were fixed with Spark-specific CSV parser options, but both exist *because* CSV has no native types and genuinely ambiguous quoting/escaping rules — not because of a mistake in how the CSV was written. Python's own `csv` module parsed both cases correctly; Spark's parser (Univocity-based) didn't, by default. Two different tools disagreeing about the same file is itself a sign the format is the weak point, not either implementation.

**Underlying all three:** the CSV ingestion scripts also hand-picked a fixed `FIELDS` list per file — meaning the "raw" layer was already a curated projection of the API response, not the true raw payload, even before the mutation mistake compounded it.

## Decision

1. **Raw ingestion format: JSON Lines (JSONL), not CSV.** One complete, unmodified API response object per line — no field selection at ingestion time. Whatever the API returns is what gets written.
2. **Raw data is write-once.** Any future correction (like the pagination dedup fix, which now happens *during* extraction in `fetch_all()`, before anything is ever written) happens at extraction time or via a fresh re-run — never by rewriting an already-landed raw file in place.
3. The CSV files that existed briefly (deduplicated, but by then already a mutation of the original) were archived to `data/archive/csv_v1/` rather than deleted, preserving the record of what happened rather than erasing it.

## Consequences

**Gained:**
- An entire class of bug eliminated, not just patched: JSON carries real native types (actual booleans, actual numbers), so the Spark script no longer needs defensive string-then-cast logic or CSV-specific parser options at all — compare this file's simplicity to the version it replaced.
- A genuinely more complete raw layer. Capturing full payloads instead of a hand-picked field list already paid off directly — fields we didn't know existed (`pool`, `mechanism`, `uniqueBettorCount`, and a `url` field we'd been reconstructing manually because we assumed the API didn't return it) are now present for free.
- A properly immutable raw layer going forward, with the practice named explicitly rather than assumed.

**Given up, plainly:** the original raw CSV snapshot — including its duplicates — is permanently lost. It can only be approximated by a fresh re-fetch, and the API's pagination instability means even that isn't guaranteed identical: a fresh markets pull returned 389 unique markets vs. 388 after deduplicating the previous run. Small, but real, and worth being able to explain honestly rather than claim perfect reproducibility that doesn't exist.

**Watch for:** full raw payloads are larger than the hand-picked CSV fields were (the bets file alone was 63MB as CSV with a reduced field set) — not a problem yet at this project's scale, but worth monitoring if it grows.
