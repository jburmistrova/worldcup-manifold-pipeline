"""Computes the Brier-score numbers behind docs/results.md's Question 1
and Question 2 (liquidity) sections. Standalone and reproducible, same as
plot_calibration.py -- re-run any time the marts change.
"""
import duckdb

DB_PATH = "dbt/manifold.duckdb"

MANIFOLD_BRIER = 0.1748

TRADE_WEIGHTED_BRIER = """
    select
        count(*) as n_trades,
        count(distinct market_id) as n_markets,
        avg(power(prob_trade - (case when is_yes then 1.0 else 0.0 end), 2)) as brier
    from mart_trade_calibration
"""

LIQUIDITY_TIERS_RAW = """
    select
        case
            when liquidity_total <= 25 then '1_low (<=25)'
            when liquidity_total <= 100 then '2_default (26-100)'
            else '3_high (>100)'
        end as liquidity_tier,
        count(*) as n,
        round(100.0 * sum(case when prob_bucket in (0.0, 0.9) then 1 else 0 end) / count(*), 1) as pct_extreme,
        avg(power(predicted_prob - (case when is_yes then 1.0 else 0.0 end), 2)) as brier
    from mart_market_efficiency
    group by 1
    order by 1
"""

LIQUIDITY_TIERS_EX_EXTREMES = """
    select
        case
            when liquidity_total <= 25 then '1_low (<=25)'
            when liquidity_total <= 100 then '2_default (26-100)'
            else '3_high (>100)'
        end as liquidity_tier,
        count(*) as n,
        avg(power(predicted_prob - (case when is_yes then 1.0 else 0.0 end), 2)) as brier
    from mart_market_efficiency
    where prob_bucket not in (0.0, 0.9)
    group by 1
    order by 1
"""


def main():
    con = duckdb.connect(DB_PATH, read_only=True)

    print("== Trade-weighted Brier score, matched to Manifold's methodology ==")
    n_trades, n_markets, brier = con.execute(TRADE_WEIGHTED_BRIER).fetchone()
    print(f"{n_markets} qualifying BINARY markets (>=15 traders), {n_trades} real trades")
    print(f"Brier score: {brier:.4f}  (Manifold platform-wide: {MANIFOLD_BRIER})")

    print("\n== Liquidity tiers, raw (confounded by prob_bucket composition) ==")
    for tier, n, pct_extreme, brier in con.execute(LIQUIDITY_TIERS_RAW).fetchall():
        print(f"{tier}: n={n}, {pct_extreme}% in extreme buckets, brier={brier:.4f}")

    print("\n== Liquidity tiers, excluding the two extreme (trivial) buckets ==")
    for tier, n, brier in con.execute(LIQUIDITY_TIERS_EX_EXTREMES).fetchall():
        print(f"{tier}: n={n}, brier={brier:.4f}")


if __name__ == "__main__":
    main()
