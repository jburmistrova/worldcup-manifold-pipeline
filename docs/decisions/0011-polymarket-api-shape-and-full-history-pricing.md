# ADR-0011: Polymarket's real API shape, and getting full-history pricing past a 10,000-trade cap

**Status:** Accepted
**Date:** 2026-08-03

## Context

With Polymarket cleared as an eligible data source (ADR-0010), pulled a small real sample before writing any production ingestion code, the same discipline ADR-0007 and ADR-0008 already established: verify the actual API shape and behavior, don't assume it mirrors Manifold's just because both are prediction markets.

**Market structure is fundamentally different, not just relabeled.** Manifold's outright-winner market is one `MULTIPLE_CHOICE` market with 50 answers under a single `market_id`. Polymarket's equivalent ("World Cup Winner") is an **event** containing 50+ separate binary markets, one per team, each its own `conditionId` and its own pair of Yes/No CLOB tokens, linked by a `negRiskMarketID`. Canonical `market_id` maps to the Polymarket event; canonical `answer_id` maps to the individual binary market, the reverse of Manifold's nesting.

**Search has the same "don't trust the query string to scope correctly" risk already documented for Manifold's Cricket World Cup contamination**, in a different form. Searching "World Cup 2026" surfaced a genuine 2022 World Cup event (`startDate: 2022-11-21`). Separately, re-running the identical search later returned a different member of the same reported `totalResults: 488`, a real result-set instability worth naming even though it wasn't fully root-caused, the same honesty ADR-0007 applied to Manifold's own unexplained-mechanism pagination bug.

**Trades carry a single execution `price` (0-1 decimal), not a paired before/after** the way Manifold's bets do:
```json
{"side": "SELL", "asset": "4394...", "size": 793.17, "price": 0.999, "timestamp": 1784510128, "outcome": "Yes"}
```
Manifold's own before/after pair turned out to be load-bearing (see the abandoned Postgres-target `LAG`-refactor: 33-37% of `MULTIPLE_CHOICE` ticks don't satisfy "this trade's before equals the previous trade's after," because `cpmm-multi-1` shares one liquidity pool across a market's answers). Checked whether the same assumption holds for Polymarket before trusting it: pulled 10,000 real trades on the Spain outright-winner token and measured trade-to-trade price jumps within each token's own sequence. Median jump ~0.001 (effectively flat), p95 ~0.01-0.016, max ~0.24-0.30, a shape consistent with a real, coherent order book, nothing like Manifold's up-to-0.96 mismatches. `LAG(price)` reconstruction holds for Polymarket specifically; the two platforms need different derivation logic, not one shared trick.

**`/trades` has a hard, undocumented-until-hit ceiling**, confirmed by the API's own error: `"max historical trades offset of 10000 exceeded"`. Trades are returned most-recent-first with no timestamp cursor, so for a popular market the reachable window can be tiny: all 10,000 trades on the Spain token, pulled via full offset pagination, spanned exactly **3.6 hours** (around the Final), not the market's actual year-plus lifetime. For this project's actual use case, pre-kickoff calibration, that's the worst possible truncation: it would keep only late, near-resolution noise and discard the early history that's the whole point of the analysis.

**`/prices-history` isn't count-capped, but it does cap request span.** `interval=max` returned a real, sane series but only 17 days, not back to the market's mid-2025 creation. An explicit wide `startTs`/`endTs` window returned zero points, not an error, initially looking like a hard data ceiling. Narrowing the window found the real cause: `"invalid filters: 'startTs' and 'endTs' interval is too long"` past roughly 20-30 days. Confirmed the earlier "zero points" wasn't a data-availability limit by requesting a narrow window right at the market's creation date and getting real data back.

## Decision

**Use `/prices-history`, chunked into 14-day windows and stitched together, as the primary source for Polymarket probability reconstruction, not `/trades`.** 14 days is comfortably inside the confirmed-working span and gives round, predictable chunk boundaries. `/trades` stays useful for genuinely trade-level detail (size, side, individual counterparties) where that resolution matters, but not as the primary source for a continuous probability series, given its recency cap.

Built and validated end-to-end on a real market before treating this as settled: `ingest/pull_polymarket_prices.py` walked the Spain outright-winner token's full lifetime (2025-07-02 to 2026-07-20) in 14-day chunks and returned 9,045 unique, hourly-cadence points with no duplicate timestamps and no chunk-boundary gaps (median gap exactly 3,600s, matching the requested 60-minute fidelity; max gap ~9 hours, a plausible low-liquidity period, not a stitching artifact). Cross-checked against known real-world outcomes: 16.5% implied probability at tournament start (Spain a mid-tier favorite among many teams), 99.95% just before the Final resolved (Spain won). Both match what actually happened.

**Only the first (`outcomeIndex` 0, confirmed empirically to always be "Yes") token per binary market gets pulled**, not both. The complementary token's price is redundant information for a canonical "probability of Yes" series, matching Manifold's own `prob = P(YES)` convention; pulling both would double every request for nothing new.

## Consequences

**Gained:** a validated, production-shaped path to full-history Polymarket pricing (`ingest/pull_polymarket_markets.py`, `pull_polymarket_trades.py`, `pull_polymarket_prices.py`, all built and tested against live data, not just sketched), and three real API behaviors documented before they could silently corrupt a downstream analysis: the 10,000-trade recency cap, the `/prices-history` span limit, and the trade-shape difference that rules out reusing Manifold's `int_market_implied_probability` logic unmodified.

**Cost:** Polymarket probability reconstruction will run at hourly granularity (`/prices-history`'s fidelity), not true tick-level like Manifold's per-trade VWAP. A real, honest difference in what's comparable between the two platforms, not something to paper over when the eventual cross-platform mart gets built.

**Not yet done:** the Spark flatten and dbt staging layers for this data, and the canonical-contract union with Manifold's own trades (`int_all_trades`, sketched in conversation, not yet built). This ADR covers the ingestion-side investigation only, the same scoping discipline ADR-0008 used (clear the data question fully before writing the modeling layer on top of it).
