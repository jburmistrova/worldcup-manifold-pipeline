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

## Question 1: does calibration here match Manifold's platform-wide numbers?

Manifold's own published calibration methodology (sampled trades on resolved binary questions with 15+ traders, checked hourly) reportedly lands realized frequencies within about 3 percentage points of market probability at every decile from 10% to 90% — a figure surfaced via web research earlier in this project, not independently verified against Manifold's raw methodology output, so treat it as directional context rather than a precise benchmark to test against statistically.

Against that rough benchmark: the well-sampled extremes here are close — the 0.9–1.0 bucket is off by about 1.1 percentage points, well inside that range. But the *direction* of the deviation matters more than its size: Manifold's own platform-wide number is an aggregate across every category (politics, economics, AI, sports, crypto), and this project's whole reason for existing was that no public breakdown exists for sports specifically, let alone a single-elimination tournament. The favorite-longshot pattern found here — strongest at the extremes — isn't something the platform-wide aggregate would necessarily reveal, since it blends categories that may not share the same bias. That's the actual answer to question 1: broadly consistent at the level Manifold reports, but this project surfaces a domain-specific pattern their aggregate number can't show either way.

## What would strengthen this

Not done here, and worth being explicit about rather than implying this is the final word:

- **The middle-bucket sample sizes are the real limitation.** More data (a longer time window, additional tournaments) would matter more than any modeling change.
- **The liquidity-vs-calibration question from the problem statement isn't analyzed here yet** — `mart_market_efficiency` carries `liquidity_total` per prediction specifically so this is possible, just not yet built. Stretch scope.
- **This uses resolution-time probability, not pre-kickoff probability** (see [ADR-0007](decisions/0007-search-limit-truncation.md) for why a true pre-kickoff analysis isn't currently viable at scale — `sportsStartTimestamp` only covers ~17% of markets).

## Reproduce it

```bash
cd dbt && dbt build --profiles-dir .
cd .. && python analysis/plot_calibration.py
```
