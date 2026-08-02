# ADR-0009: Stretch marts (match price history, outright odds), and the near-duplicate outright market problem

**Status:** Accepted
**Date:** 2026-08-02

## Context

`mart_match_price_history` and `mart_outright_odds_over_time` were the two stretch marts named in the original architecture (`PROJECT_SPEC.md`): win-probability movement through each match, and how the tournament-winner contract repriced over the tournament. Neither is load-bearing for the core problem statement, both `mart_market_efficiency` and `mart_pre_kickoff_calibration` already answer it, but both are a genuine additional demonstration of the same reconstruction work.

**Checked the data before writing either mart, same standard as ADR-0008.**

For `mart_match_price_history`: the "each match" scope already exists and is already validated. `int_market_kickoff_times` (ADR-0008) identifies exactly which markets/answers are genuine single-match questions, matched by strict pattern and confirmed 108-of-108 against Manifold's own kickoff data. No new matching logic was needed, just reusing that validated set.

For `mart_outright_odds_over_time`: assumed, going in, that there'd be one clear "who wins the World Cup" market. There wasn't. A search for World Cup winner/champion markets turned up roughly 15 separate `MULTIPLE_CHOICE` markets with near-identical phrasing ("Who will win the 2026 FIFA World Cup?", "Which team will win the 2026 FIFA World Cup?", "World cup 2026 winner," and so on), almost certainly independent markets created by different users rather than one canonical contract. Checked volume, liquidity, and bet count for each rather than picking one by name-match alone:

| Market | Volume | Real bets | Answers |
|---|---|---|---|
| "2026 FIFA World Cup ⚽ \| 🏆 Winner" | $1,652,691 | 18,293 | 50 |
| "Which Team will win the 2026 FIFA World Cup?" | $150,183 | 4,076 | 43 |
| "Which country will win the 2026 FIFA World Cup?" | $103,878 | 2,546 | 41 |
| (12 more, all under $100K, several under $20K) | | | |

One market is an order of magnitude ahead of every other candidate on every measure. Not a close call requiring a judgment threshold, a real, checkable gap.

## Decision

1. **`mart_outright_odds_over_time` scopes to the single dominant market** (`JRzL2QcArhM674YSO4d8`), hardcoded by ID with the volume comparison documented here, not resolved by picking "the" market with a fuzzy name match or by unioning every candidate together. Unioning all ~15 would mix one real price-discovery market with fourteen mostly-untraded duplicates, diluting the signal rather than adding coverage. If a future need called for the fuller picture (comparing how odds diverged across near-duplicate markets), that would be a deliberately different mart, not a silent expansion of this one.

2. **Extracted `int_answer_kickoff_times`** out of `int_pre_kickoff_probability`, where the market-level-to-answer fan-out logic (see ADR-0008's `int_market_kickoff_times`) originally lived inline. `mart_match_price_history` needed the identical fan-out to scope its own join. Two consumers needing the same logic is the same trigger that justified extracting the `prob_bucket` macro earlier: duplicate it once, and it can drift out of sync the next time either query changes.

3. **Both new marts reuse `int_market_implied_probability` directly**, no new reconstruction logic. `mart_match_price_history` and `mart_outright_odds_over_time` differ only in which rows they select and which descriptive columns (team names, kickoff time, resolution) they attach, keeping with the project's existing intermediate/mart split: reconstruction is intermediate-layer work, done once; a mart's job is presentation-shaped selection, not recomputation.

## Consequences

**Gained:** 67,546 rows of match-level price history across 386 validated market/answer pairs, and 18,293 rows of outright-market price history across 50 countries, both queryable and contract-enforced like the existing marts.

**A real limitation, stated plainly:** `mart_outright_odds_over_time` represents one market's view of the tournament-winner odds, not the platform's aggregate view. The ~14 other near-duplicate markets each had their own (much thinner) trading and their own probabilities, which could disagree with the dominant market's at any given time. This mart doesn't reconcile or average across them, it reports the one market where that disagreement would matter least, because it's where almost all the real activity happened.

**Deliberately not attempted:** no attempt to identify or merge near-duplicate markets programmatically for other prop-bet categories (Golden Boot, group winners, etc.) that likely have the same fragmentation. Out of scope for two stretch marts; would be its own investigation if ever needed.
