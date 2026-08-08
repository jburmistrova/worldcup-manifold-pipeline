# ADR-0013: Real-money vs. play-money calibration comparison, a deliberate exception to keeping this project DE-scoped

**Status:** Accepted
**Date:** 2026-08-04

## Context

With Manifold and Polymarket both flowing through the same canonical schema (ADR-0012), the original motivating question for adding Polymarket at all became answerable: are people more "fast and loose," worse-calibrated, with fake money than real money, and is any difference statistically meaningful.

**This is a genuine exception, not a scope drift.** Earlier in this project, a bootstrap significance test (a different comparison: bucketed calibration within Manifold alone) was built, then deliberately removed after concluding it "veers too much into a data science question and not a data engineer question." Asked directly whether to build formal significance testing again for this cross-platform question, the choice was made explicitly, not by default: do the real statistical test, as a conscious one-off exception, not a quiet reversal of the earlier call.

**Scope had to be narrowed to make this answerable at all**, not just to keep it small. Manifold and Polymarket's full datasets aren't directly comparable: most of Polymarket's ~6,358 markets don't have a clean single "kickoff" moment the way an individual match does (props, tournament-wide bets, player-performance markets), and replicating ADR-0008's full kickoff-time-matching effort for Polymarket would be its own multi-day project with no guarantee of a comparably-clean result. Both platforms do have one genuinely comparable event, though: an outright World Cup winner market, same real-world outcome (Spain), unambiguous ground truth, on both sides.

**Resolution-time was rejected as the comparison point for the same reason it was rejected in ADR-0008/docs/results.md's Question 1.** By the time a market resolves, it already knows the outcome; a resolution-time Brier score mostly measures how fast a platform's price mechanically converges to the known answer, not genuine belief under real uncertainty, the actual thing "fast and loose with fake money" is asking about. Used each team's last real implied probability strictly before the tournament itself started (2026-06-11 19:00 UTC, the real first match kickoff, confirmed against `stg_worldcup_schedule` rather than assumed from a rounder-sounding date like the Opening Ceremony) instead.

## Decision

**Built `mart_platform_calibration_comparison`**: one row per team's outright-winner prediction on each platform, at the pre-tournament snapshot described above. Manifold's `is_yes` uses the same single-select-resolution derivation established in `mart_outright_odds_over_time` (the market's own `resolution` field holds the winning `answer_id`, confirmed empirically here too: all 50 of Manifold's own answer-level `resolution` values were `NULL`); Polymarket's is already correctly self-contained per market (confirmed: 59 `NO`, 1 `YES`, matching Spain's real win).

**Built `analysis/compare_platform_calibration.py`**: a bootstrap significance test, not a simple two-sample comparison. Resamples each platform's own sample independently (preserving group structure, not pooling), 10,000 iterations, builds an empirical distribution for the difference in Brier scores, reports a 95% percentile CI and an approximate two-sided p-value.

## Result

**Manifold: n=47, Brier=0.0162. Polymarket: n=50, Brier=0.0152.** Observed difference (Manifold minus Polymarket): 0.0010, Manifold nominally worse-calibrated, in the direction the "fast and loose with fake money" hypothesis would predict. **95% bootstrap CI: [-0.0402, 0.0422]. Approximate p-value: 0.83.** The CI comfortably includes zero: **no statistically significant difference detected.**

## Consequences

**The honest, unavoidable limitation, stated plainly rather than glossed over:** n=47 and n=50, with exactly one true positive per platform (one team wins). This is a small, low-power sample by construction, not an oversight, resampling a set this size and this imbalanced can occasionally draw zero positives in a single bootstrap iteration, part of why the resulting interval is as wide as it is. A wide, zero-including CI at this sample size is close to the most likely outcome regardless of whether a real underlying difference exists; this result can rule out a *large* difference between the platforms on this specific comparison, it cannot rule out a small one.

**What this doesn't answer:** whether real money produces better-calibrated forecasting in general. The observed direction (Manifold nominally worse) is consistent with the "fast and loose" hypothesis, but "consistent with" and "confirms" are different claims, and this project's own standing preference for real, checkable data-source and methodology diligence applies here too: a non-significant result on 97 total observations is not evidence of no effect, it's an honest statement that this specific comparison, at this specific scope, couldn't detect one.

## Update (2026-08-04): "play money" was imprecise, checked against Manifold's actual policy

Manifold's own description of Mana states you can acquire it by "claiming your free starting balance, making successful prediction trades, completing daily quests, referring friends, or purchasing more directly with cash." That last clause matters: real dollars genuinely flow into Manifold. Calling it simply "fake money," as this ADR's Context and Result sections do, overstates how disconnected Mana actually is from real currency.

**Checked Manifold's actual conversion policy directly rather than assumed one way or the other.** Confirmed: Mana is one-way convertible. Cash buys Mana; Mana cannot be converted back to USD, crypto, or gift cards under any circumstance. The only exit is a fixed-rate charitable donation (Ṁ100 = $1), not a cash-out. Manifold previously ran a "Sweepcash" program permitting real-money withdrawal; it's been discontinued. Manifold states the one-way restriction is deliberate, it's specifically what keeps the platform outside the standard US legal test for gambling.

**This changes which dimension of "real vs. fake" the comparison is actually testing.** Cash-in was never the relevant asymmetry, whether a trader can realize monetary *profit* from being right is. A Polymarket trader who's correct can withdraw real gains; a Manifold trader who's correct can only get more Mana, spendable inside the platform or donated at a fixed rate, never converted to personal profit. That's the actual "skin in the game" mechanism prediction-market theory points to for why real money might sharpen forecasting (see the Kyle-model discussion in Wolfers & Zitzewitz 2006, `docs/results.md`'s citation [2]), and it holds regardless of whether cash went in on the Manifold side.

**More accurate framing, going forward: two-way-convertible real money (Polymarket) vs. one-way-convertible, profit-inextractable currency (Manifold), not "real vs. fake."** The comparison built in this ADR is still meaningful under the corrected framing, arguably more precisely meaningful, since the actual mechanism being tested (profit-motivated accuracy) is now correctly identified rather than conflated with "has monetary value at all."

