# ADR-0012: A canonical cross-platform trade schema, built and validated on a real 60-market sample

**Status:** Accepted
**Date:** 2026-08-03

## Context

With Polymarket's real API shape understood (ADR-0011), the next question was how to feed its data into `int_market_implied_probability` without forking that model's actual reconstruction logic (VWAP, repricing-jump rank) per platform. The two platforms' trade data isn't just differently named, it's structurally different: Manifold's bets already carry a `prob_before`/`prob_after` pair per trade (an AMM reprices atomically within one trade); Polymarket's price samples carry one value, with `prob_before` only recoverable by comparing to the prior sample.

**Market identity also doesn't map 1:1.** Manifold's outright-winner market is one `MULTIPLE_CHOICE` market with 50 answers under a single `market_id`. Polymarket's equivalent event contains 50+ separate binary markets, one per team, linked by `negRiskMarketID`, not nested under one parent id.

## Decision

**One shared intermediate model, `int_all_market_ticks`, unions both platforms into a single canonical shape** (`market_id`, `answer_id`, `bet_id`, `created_at`, `amount`, `prob_before`, `prob_after`, `source_platform`). `int_market_implied_probability` reads from it instead of `stg_manifold_bets` directly; its own logic is otherwise completely unchanged.

**Manifold's real `prob_before`/`prob_after` pass through unmodified.** Briefly considered deriving both platforms' before/after the same way (`LAG()` on one shared value), rejected once real data showed why: checking 208,210 real Manifold ticks found 33-37% of `MULTIPLE_CHOICE` ticks don't satisfy "this trade's before equals the previous trade's after," because `cpmm-multi-1` shares one liquidity pool across a market's answers, a trade on one answer moves its siblings too, invisible to a same-answer-only `LAG()`. Manifold's own reported values already reflect the true AMM state; discarding them for a shared derivation would have been a real accuracy regression to gain code reuse that wasn't worth the trade.

**Polymarket's `prob_before`/`prob_after` are derived via `LAG(price)` per (market, answer), specific to Polymarket, not shared with Manifold's logic.** Validated as sound before trusting it: 10,000 real trades on the Spain outright-winner token showed a median trade-to-trade jump of ~0.001 and a max of ~0.30, nothing like Manifold's up-to-0.96 mismatches. Each Polymarket outcome is its own independent CLOB order book, no equivalent cross-answer coupling found.

**`amount` is `NULL` for every Polymarket row.** A price sample has no size, unlike an executed trade. `int_market_implied_probability`'s VWAP weighting has nothing real to weight by for these rows; standard SQL's own `NULL` handling in `SUM()` correctly leaves `prob_vwap_running` `NULL` for Polymarket without any special case in that model, a fabricated equal-weight average was considered and rejected as a plausible-looking wrong number.

**Canonical `market_id`/`answer_id` for Polymarket follow Manifold's own BINARY/MULTIPLE_CHOICE convention**: `coalesce(negRiskMarketID, market_id)` as `market_id`, the individual market's own id as `answer_id` only when it belongs to a negRisk group, `NULL` otherwise, mirroring how a Manifold BINARY market's `answer_id` is `NULL` too.

## Two real bugs found building this, not assumed away

**A `bet_id` collision across markets, not platforms.** The synthesized Polymarket id used `'pm-' || row_number()`, prefixed specifically to avoid colliding with Manifold's real bet IDs, but `row_number()` resets to 1 for every `(market_id, answer_id)` partition, so "pm-1" collided across all 60 sample markets, 8,882 real duplicates caught by the model's own uniqueness test on the first build, not shipped unnoticed. Fixed by folding the market/answer identity into the generated id itself.

**A silent `TIMESTAMP WITH TIME ZONE` vs `TIMESTAMP` mismatch.** DuckDB's `to_timestamp()` returns a timezone-aware type; Manifold's own `epoch_ms()`-derived columns are timezone-naive. Both represent UTC in spirit, but they're different SQL types, caught by an enforced contract failing once the two were unioned, not by inspection. Fixed by explicitly casting Polymarket's timestamps down to plain `TIMESTAMP` in staging.

## Consequences

**Gained:** a validated, working cross-platform reconstruction layer. Built and checked against a real 60-market sample (the outright-winner event, not synthetic data): `int_all_market_ticks` unions 212,749 Manifold ticks with 295,535 Polymarket ticks cleanly, and the Spain market's full reconstructed path (9,045 ticks) through the entire chain, Spark through `int_market_implied_probability`, matches the same real values independently validated in ADR-0011 (first tick 0.15, last tick 0.9995, Spain's actual outcome).

**Not yet done:** scaled to the full ~6,359-market Polymarket dataset (this ADR's sample is 60 markets, one event); the actual cross-platform comparison mart this whole effort exists to eventually support.
