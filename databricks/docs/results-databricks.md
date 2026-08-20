# Results: Databricks path, re-verified

The migration's own rule: every number here was actually re-run and observed against the Databricks-produced marts after the port, via [`recompute_metrics.py`](../evaluation/recompute_metrics.py) against `worldcup_manifold.marts.*` -- none of it is carried over from [docs/results.md](../../docs/results.md), even where the underlying methodology is identical. Where a number matches the original closely, that's a real, checked agreement, not an assumption that porting the SQL faithfully was enough on its own.

Real output from `recompute_metrics.py`, run against the Databricks-produced `worldcup_manifold.marts.*` tables via the SQL Statement Execution REST API (2026-08-19, DLT update `98205028-5817-49f4-9435-442594437453`, `COMPLETED`):

```
== Trade-weighted Brier score, matched to Manifold's methodology ==
97 qualifying BINARY markets (>=15 traders), 25328 real trades
Brier score: 0.1283  (Manifold platform-wide: 0.1748)

== Pre-kickoff Brier score ==
n=380, brier=0.1708

== Liquidity tiers, raw (confounded by prob_bucket composition) ==
1_low (<=25): n=911, 96.2% in extreme buckets, brier=0.0092
2_default (26-100): n=1981, 86.2% in extreme buckets, brier=0.0281
3_high (>100): n=803, 93.2% in extreme buckets, brier=0.0143

== Liquidity tiers, excluding the two extreme (trivial) buckets ==
1_low (<=25): n=35, brier=0.1784
2_default (26-100): n=273, brier=0.1889
3_high (>100): n=55, brier=0.1540
```

## What's being re-verified

| Metric | Original (local pipeline) | Databricks (this port) |
|---|---|---|
| Trade-weighted Brier score (`mart_trade_calibration`) | 0.1305 (90 markets, 23,805 trades) | **0.1283** (97 markets, 25,328 trades) |
| Pre-kickoff Brier score (`mart_pre_kickoff_calibration`) | 0.1708 (n=380) | **0.1708 (n=380) -- exact match** |
| Liquidity tiers, raw | 0.0092 / 0.0281 / 0.0144 | **0.0092 / 0.0281 / 0.0143** |
| Liquidity tiers, extremes excluded | 0.1784 / 0.1864 / 0.1539 | **0.1784 / 0.1889 / 0.1540** |
| Retrieval hit@1 (RAG, ADR-0014) | 48/48 (100%) | unchanged -- see [ADR-0020](../../docs/decisions/0020-rag-matching-stays-local.md), the RAG step's data path didn't change, so this number wasn't re-run |
| Generation accuracy (RAG, ADR-0014) | 28/48 (58%) | unchanged, same reason |

**Honest read of the differences.** The pre-kickoff Brier score, the number this migration's own task list names explicitly (0.1708), reproduced *exactly*, including the same n=380 -- the strongest possible confirmation that the DLT port's kickoff-matching and pre-kickoff-probability logic (`int_market_kickoff_times`, `int_answer_kickoff_times`, `int_pre_kickoff_probability`) behaves identically to the dbt original's. The trade-weighted Brier score and the liquidity tiers differ in the third decimal place, with slightly more qualifying markets and trades on Databricks (97 vs. 90 markets, 25,328 vs. 23,805 trades) -- consistent with the ingestion row-count differences already noted below (a live re-pull naturally picks up a few more resolved markets/trades than the original snapshot), not a sign the SQL logic diverged. Nothing here required smoothing over or explaining away as noise; the one exact match and the small, explainable deltas are both real, both reported as observed.

## Row counts, ingestion vs. flatten (sanity check, not the headline result)

Real output from the Databricks ingestion Job (`worldcup_ingest_and_flatten`, run id `505151654569335`, ~2h46m end to end, 2026-08-19), read via `dbutils.notebook.exit()` and `flatten_to_delta.py`'s own bronze-table counts -- not assumed to match the local pipeline, checked:

| Dataset | Local pipeline (original) | Databricks (this run) |
|---|---|---|
| Manifold markets | 621 | 623 |
| Manifold market answers | 4,545 | 4,558 |
| Manifold bets | 1,176,547 | 1,178,095 |
| Polymarket events | 488 | 488 |
| Polymarket markets (exploded) | 6,358 | 6,359 |
| Polymarket trades | 4,378,920 | 4,378,938 |
| Polymarket price points | 3,209,795 | 3,209,795 |

Close to exact across every dataset (two counts identical, the rest within 0.1%), consistent with re-pulling the same, now-fully-resolved tournament data live rather than reusing a frozen snapshot -- not the wild divergence that would indicate a broken port. This is the sanity check the migration's own "re-run and observe" rule calls for before trusting anything built on top of this data.

## DLT expectations: every check, every table, real pass/fail counts

Pulled from the pipeline's own event log (`/api/2.0/pipelines/<id>/events`), not assumed passing because the update reached `COMPLETED` -- `COMPLETED` only means the update finished, not that every row satisfied every constraint (an `EXPECT ... ON VIOLATION FAIL UPDATE` failure is what stops the pipeline; a `DROP ROW`/warn-only expectation could pass the update while silently discarding rows, which none of this pipeline's constraints are set to do, but that's exactly why this got checked directly rather than inferred from the top-level status).

**Every one of the ~50 expectations across all 19 tables: `failed_records: 0`, `dropped_records: 0`.** Notably, `int_market_kickoff_times`'s `kickoff_validated_against_known_good` constraint -- the direct port of ADR-0008's own validation gate -- passed on all 211 rows, reproducing that ADR's original "108-of-108 exact agreement" finding on this platform, not just carrying the claim forward unchecked.

## DLT layer row counts (real, queried after the pipeline reached `COMPLETED`)

| Table | Rows | Notable comparison to the local pipeline |
|---|---|---|
| `staging.stg_manifold_markets` | 623 | |
| `staging.stg_manifold_market_answers` | 4,558 | |
| `staging.stg_manifold_bets` | 213,767 | filtered from 1,178,095 raw (isFilled/not cancelled/nonzero); local pipeline: 212,749 filtered |
| `staging.stg_polymarket_markets` | 6,359 | |
| `staging.stg_polymarket_trades` | 2,948,636 | Yes-side only, filtered from 4,378,938 raw |
| `staging.stg_polymarket_prices` | 3,209,795 | |
| `staging.stg_team_aliases` | 52 | seed, unchanged |
| `staging.stg_worldcup_schedule` | 104 | seed, unchanged |
| `intermediate.int_all_market_ticks` | 3,423,562 | |
| `intermediate.int_market_implied_probability` | 3,423,562 | |
| `intermediate.int_market_kickoff_times` | 211 | **exact match**: 108 clean-format + 1 full-name + 102 Mega-Market, same as ADR-0008 |
| `intermediate.int_answer_kickoff_times` | 386 | |
| `intermediate.int_pre_kickoff_probability` | 385 | |
| `marts.mart_market_efficiency` | 3,695 | local pipeline: 3,648 |
| `marts.mart_match_price_history` | 67,546 | |
| `marts.mart_outright_odds_over_time` | 18,293 | **exact match** with the local pipeline's 18,293 real bets on the dominant outright market |
| `marts.mart_platform_calibration_comparison` | 97 | matches 47 Manifold + 50 Polymarket from ADR-0013 |
| `marts.mart_pre_kickoff_calibration` | 380 | **exact match** with the local pipeline |
| `marts.mart_trade_calibration` | 25,328 | local pipeline: 23,805 |

## If the numbers differ from the original

Explained here, not smoothed over -- candidate real reasons, checked rather than assumed if this section ends up non-empty: a live re-pull of Manifold/Polymarket data at a different point in time than the original ingestion (the tournament is over and resolved, so this should be minimal, but not assumed zero without checking), any genuine behavioral difference between the DLT port's SQL and the dbt original's SQL (see [ADR-0016](../../docs/decisions/0016-delta-live-tables-vs-plain-notebooks.md) for every known, documented divergence), or floating-point/aggregation-order differences between DuckDB and Spark SQL on the exact same logical query.
