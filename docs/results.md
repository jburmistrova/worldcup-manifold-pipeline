# Results: Calibration and the Favorite-Longshot Bias

This is the evidence the pipeline produces something real — not just that it runs, but that it answers the two questions from the [problem statement](architecture.md#problem-statement). Generated from [`mart_market_efficiency`](../dbt/models/marts/mart_market_efficiency.sql) via [`analysis/plot_calibration.py`](../analysis/plot_calibration.py); re-running that script regenerates this chart from whatever the mart currently contains, not a one-off snapshot.

![Calibration chart: predicted probability vs. actual resolution rate](images/calibration_chart.png)

## The numbers behind the chart

| Predicted bucket | n | Avg predicted | Actual YES rate |
|---|---|---|---|
| 0.0–0.1 | 1,647 | 1.5% | 0.0% |
| 0.1–0.2 | 52 | 15.0% | 1.9% |
| 0.2–0.3 | 33 | 25.3% | 15.2% |
| 0.3–0.4 | 38 | 34.4% | 34.2% |
| 0.4–0.5 | 34 | 44.9% | 44.1% |
| 0.5–0.6 | 51 | 55.0% | 49.0% |
| 0.6–0.7 | 27 | 65.7% | 66.7% |
| 0.7–0.8 | 17 | 75.8% | 76.5% |
| 0.8–0.9 | 32 | 85.6% | 87.5% |
| 0.9–1.0 | 900 | 98.6% | 99.7% |

2,831 resolved predictions total — 388 `BINARY` markets plus every resolved `MULTIPLE_CHOICE` answer, unioned in `mart_market_efficiency`.

## Question 2: does the favorite-longshot bias show up?

**Yes, and it's the textbook shape.** At the low end (longshots — predicted probability near 0), actual outcomes happen *less* often than predicted: the 0.1–0.2 bucket predicted 15.0% on average but only 1.9% of those predictions actually resolved YES. At the high end (favorites), actual outcomes happen slightly *more* often than predicted: the 0.9–1.0 bucket, the largest and best-sampled in the dataset, predicted 98.6% and came in at 99.7%. The middle of the curve (0.3–0.5) sits close to the diagonal — near-perfect calibration. That's exactly the pattern the literature describes: the bias concentrates at the extremes and fades toward the middle, not a uniform effect across the whole probability range.

**Honest statistical caveat:** sample sizes are wildly uneven, and this matters for how much to trust each point. The two extreme buckets (1,647 and 900 predictions) are genuinely robust. The middle buckets range from 17 to 52 predictions each — thin enough that some of the wobble there (e.g., the 0.5–0.6 bucket sitting visibly below the diagonal while its neighbors don't) could easily be noise rather than signal. The part of this result I'd stand behind confidently is specifically the two extremes — which happen to be both the best-sampled *and* the most textbook-matching, which is itself a reason for confidence, not a coincidence to wave away.

### Does liquidity predict better calibration?

The problem statement's real question here: does market liquidity actually predict better calibration, or does that relationship hold up as poorly as some existing research suggests? `mart_market_efficiency` carries `liquidity_total` per prediction specifically to test this. Split into three tiers based on the actual distribution of `liquidity_total` (which clusters hard around Manifold's default market-creation subsidies, 25/100/1000 — this is closer to a discrete creation-time tier than a smooth measure of trading depth, worth naming up front): low (≤25), default (26–100, where 1,821 of 2,831 predictions sit), and high (>100).

| Liquidity tier | n | % in extreme buckets | Brier (raw) |
|---|---|---|---|
| Low (≤25) | 805 | 96.0% | 0.0095 |
| Default (26–100) | 1,821 | 87.8% | 0.0224 |
| High (>100) | 205 | 85.4% | 0.0199 |

**At face value, low liquidity looks *better* calibrated — the opposite of what you'd expect, and a red flag rather than a finding.** The same confound from Question 1 is at work: low-liquidity predictions are 96% concentrated in the two trivially-easy extreme buckets (near-certain long-shots that correctly resolved NO), so their Brier score is low because the predictions were easy, not because low-liquidity markets are genuinely better-calibrated.

**Controlling for it** — excluding the two extreme buckets, same fix as Question 1:

| Liquidity tier | n | Brier (extremes excluded) |
|---|---|---|
| Low (≤25) | 32 | 0.1738 |
| Default (26–100) | 222 | 0.1761 |
| High (>100) | 30 | 0.1323 |

**Once the confound is removed, the three tiers land in roughly the same range** (0.13–0.18) — no clear, credible relationship between liquidity and calibration quality in this dataset. The high-liquidity tier does come in a bit lower, but n=30 is far too thin to call that a real effect rather than noise; two of the three tiers (low and high) have well under 35 observations once the easy predictions are excluded. **Bottom line: the liquidity-calibration relationship holds up poorly here too** — consistent with the problem statement's framing that this relationship is often weaker than assumed — but this is closer to "no signal found, with limited power to find one" than a confident null result. Reproducible via [`analysis/compute_calibration_metrics.py`](../analysis/compute_calibration_metrics.py).

## Question 1: does calibration here match Manifold's platform-wide numbers?

Manifold publishes a live calibration page (`manifold.markets/calibration`) with a real, checkable number: **Brier score 0.1748**, computed hourly over a 2% sample of trades on resolved binary questions with 15+ traders (~97,000 trades). Their own stated method, quoted directly: "sample 2% of all past trades on resolved binary questions with 15 or more traders," using "the average probability between the start and end" of each trade as that trade's prediction, then bucketing trades by that probability and checking how often markets in each bucket actually resolved YES.

**First attempt, and why it was wrong.** The first version of this comparison used `mart_market_efficiency` — one row per resolved prediction, at its resolution-time probability — and got 0.0185 overall (0.0437 excluding a dominant easy bucket). That's not the same measurement Manifold publishes: it's market-grained and snapshot-in-time, not trade-grained and lifetime-weighted, and it included `MULTIPLE_CHOICE` answers that Manifold's "binary questions" population excludes. The two numbers looked comparable because they're both called "Brier score," but they weren't measuring the same thing — worth naming plainly rather than quietly swapping in a better number.

**Matched methodology.** Built [`mart_trade_calibration`](../dbt/models/marts/mart_trade_calibration.sql): one row per real trade on a resolved `BINARY` market with 15+ distinct traders, predicted probability = `(prob_before + prob_after) / 2` (Manifold's exact "average probability between the start and end" definition), actual outcome = that market's final resolution. The one deliberate deviation: we use *every* qualifying trade rather than a 2% sample — Manifold subsamples because they're recomputing this hourly across their whole platform's trade history, a performance tradeoff that doesn't apply to a dataset this size. Using the full population is more precise, not a departure from the method's intent.

**Result: 90 qualifying `BINARY` markets, 23,805 real trades. Brier score = 0.1305**, vs. Manifold's 0.1748. Still better, but now by a believable margin — not the suspicious ~10x gap the first, mismatched comparison produced. That gap between the two comparison attempts is itself the more interesting finding: most of the earlier "our calibration is way better" result was a measurement artifact, not a real effect. Reproducible via [`analysis/compute_calibration_metrics.py`](../analysis/compute_calibration_metrics.py).

**Honest bottom line:** even the matched 0.1305 is directionally better than 0.1748, but I still wouldn't lean hard on the exact gap. Manifold's platform-wide number blends every category (politics, economics, AI, sports, crypto) — this project's whole reason for existing was that no public breakdown exists for sports specifically, so the two populations aren't identical even with matched math. The favorite-longshot bias finding (Question 2, above) remains the more solid, better-supported result in this project.

## What would strengthen this

Not done here, and worth being explicit about rather than implying this is the final word:

- **The middle-bucket sample sizes are the real limitation.** More data (a longer time window, additional tournaments) would matter more than any modeling change. Same limitation shows up sharper in the liquidity breakdown above — two of three tiers drop to n=30ish once the easy predictions are excluded.
- **This uses resolution-time probability for the favorite-longshot chart, not pre-kickoff probability** (see [ADR-0007](decisions/0007-search-limit-truncation.md) for why a true pre-kickoff analysis isn't currently viable at scale — `sportsStartTimestamp` only covers ~17% of markets).

## Reproduce it

```bash
cd dbt && dbt deps && dbt build --profiles-dir .
cd .. && python analysis/plot_calibration.py
python analysis/compute_calibration_metrics.py
```
