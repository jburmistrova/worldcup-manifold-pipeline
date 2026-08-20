"""Re-verifies the calibration metrics in docs/results.md against the
Databricks-produced marts, independently of the local numbers -- not a
carried-forward copy. Mirrors analysis/compute_calibration_metrics.py's
queries exactly (same Brier formula, same liquidity-tier boundaries), run
against worldcup_manifold.marts.*.

Uses the SQL Statement Execution REST API directly (requests + polling),
not the databricks-sql-connector library: the connector's Thrift-based
protocol hung indefinitely in this environment (confirmed -- even its
initial connect() never returned inside a 2-minute window), while the
plain REST API (the same one the `databricks` CLI itself uses under
`databricks api post /api/2.0/sql/statements`) worked reliably for every
other query this migration ran. A real, environment-specific finding, not
a style preference.

Run from the repo root, with DATABRICKS_HOST / DATABRICKS_TOKEN set and a
SQL warehouse id (from `databricks warehouses list`):

    pip install requests
    export DATABRICKS_WAREHOUSE_ID=<warehouse-id>
    python databricks/evaluation/recompute_metrics.py
"""
import os
import time

import requests

CATALOG = os.environ.get("DATABRICKS_CATALOG", "worldcup_manifold")
WAREHOUSE_ID = os.environ["DATABRICKS_WAREHOUSE_ID"]
HOST = os.environ["DATABRICKS_HOST"].rstrip("/")
TOKEN = os.environ["DATABRICKS_TOKEN"]


def run_query(statement):
    """Submit a statement, poll until it finishes, return (columns, rows)."""
    resp = requests.post(
        f"{HOST}/api/2.0/sql/statements",
        headers={"Authorization": f"Bearer {TOKEN}"},
        json={"warehouse_id": WAREHOUSE_ID, "statement": statement, "wait_timeout": "30s"},
    )
    resp.raise_for_status()
    data = resp.json()
    statement_id = data["statement_id"]

    while data["status"]["state"] in ("PENDING", "RUNNING"):
        time.sleep(2)
        resp = requests.get(
            f"{HOST}/api/2.0/sql/statements/{statement_id}",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        resp.raise_for_status()
        data = resp.json()

    if data["status"]["state"] != "SUCCEEDED":
        raise RuntimeError(f"Query failed: {data['status']}")

    columns = [c["name"] for c in data["manifest"]["schema"]["columns"]]
    rows = data.get("result", {}).get("data_array", [])
    return columns, rows

MANIFOLD_BRIER = 0.1748

TRADE_WEIGHTED_BRIER = f"""
    select
        count(*) as n_trades,
        count(distinct market_id) as n_markets,
        avg(power(prob_trade - (case when is_yes then 1.0 else 0.0 end), 2)) as brier
    from {CATALOG}.marts.mart_trade_calibration
"""

LIQUIDITY_TIERS_RAW = f"""
    select
        case
            when liquidity_total <= 25 then '1_low (<=25)'
            when liquidity_total <= 100 then '2_default (26-100)'
            else '3_high (>100)'
        end as liquidity_tier,
        count(*) as n,
        round(100.0 * sum(case when prob_bucket in (0.0, 0.9) then 1 else 0 end) / count(*), 1) as pct_extreme,
        avg(power(predicted_prob - (case when is_yes then 1.0 else 0.0 end), 2)) as brier
    from {CATALOG}.marts.mart_market_efficiency
    group by 1
    order by 1
"""

LIQUIDITY_TIERS_EX_EXTREMES = f"""
    select
        case
            when liquidity_total <= 25 then '1_low (<=25)'
            when liquidity_total <= 100 then '2_default (26-100)'
            else '3_high (>100)'
        end as liquidity_tier,
        count(*) as n,
        avg(power(predicted_prob - (case when is_yes then 1.0 else 0.0 end), 2)) as brier
    from {CATALOG}.marts.mart_market_efficiency
    where prob_bucket not in (0.0, 0.9)
    group by 1
    order by 1
"""

# Not yet a script on the local pipeline either (docs/results.md computed
# this inline); included here since it's one of the three headline numbers
# task 5 names explicitly (0.1708).
PRE_KICKOFF_BRIER = f"""
    select
        count(*) as n,
        avg(power(predicted_prob - (case when is_yes then 1.0 else 0.0 end), 2)) as brier
    from {CATALOG}.marts.mart_pre_kickoff_calibration
"""


def main():
    print("== Trade-weighted Brier score, matched to Manifold's methodology ==")
    _, rows = run_query(TRADE_WEIGHTED_BRIER)
    n_trades, n_markets, brier = rows[0]
    print(f"{n_markets} qualifying BINARY markets (>=15 traders), {n_trades} real trades")
    print(f"Brier score: {float(brier):.4f}  (Manifold platform-wide: {MANIFOLD_BRIER})")

    print("\n== Pre-kickoff Brier score ==")
    _, rows = run_query(PRE_KICKOFF_BRIER)
    n, brier = rows[0]
    print(f"n={n}, brier={float(brier):.4f}")

    print("\n== Liquidity tiers, raw (confounded by prob_bucket composition) ==")
    _, rows = run_query(LIQUIDITY_TIERS_RAW)
    for tier, n, pct_extreme, brier in rows:
        print(f"{tier}: n={n}, {pct_extreme}% in extreme buckets, brier={float(brier):.4f}")

    print("\n== Liquidity tiers, excluding the two extreme (trivial) buckets ==")
    _, rows = run_query(LIQUIDITY_TIERS_EX_EXTREMES)
    for tier, n, brier in rows:
        print(f"{tier}: n={n}, brier={float(brier):.4f}")


if __name__ == "__main__":
    main()
