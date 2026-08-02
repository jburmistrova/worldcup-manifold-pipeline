"""Reads mart_market_efficiency, produces the calibration chart used in
docs/results.md. Standalone and reproducible, not a one-off; re-run this
any time the mart changes and the chart updates to match.
"""
import os

import duckdb
import matplotlib.pyplot as plt

DB_PATH = "dbt/manifold.duckdb"
OUT_PATH = "docs/images/calibration_chart.png"

QUERY = """
    select
        prob_bucket,
        count(*) as n,
        avg(predicted_prob) as avg_predicted,
        avg(case when is_yes then 1.0 else 0.0 end) as actual_rate
    from mart_market_efficiency
    group by 1
    order by 1
"""


def main():
    con = duckdb.connect(DB_PATH, read_only=True)
    rows = con.execute(QUERY).fetchall()

    buckets, ns, predicted, actual = zip(*rows)

    fig, ax = plt.subplots(figsize=(7, 7))

    # perfect-calibration reference line
    ax.plot([0, 1], [0, 1], linestyle="--", color="gray", linewidth=1, label="Perfect calibration")

    # marker size scales with sqrt(n) so the two well-sampled extreme
    # buckets (1,647 and 900 predictions) read as visibly more confident
    # than the thin middle buckets (17-52 predictions each), without the
    # size difference becoming so extreme it's unreadable
    sizes = [30 * (n ** 0.5) for n in ns]
    ax.scatter(predicted, actual, s=sizes, alpha=0.7, color="#2b6cb0", edgecolor="white", zorder=3)

    for x, y, n in zip(predicted, actual, ns):
        ax.annotate(f"n={n}", (x, y), textcoords="offset points", xytext=(8, -4), fontsize=8, color="#555")

    ax.set_xlim(-0.02, 1.02)
    ax.set_ylim(-0.02, 1.02)
    ax.set_xlabel("Predicted probability (market, at resolution)")
    ax.set_ylabel("Actual resolution rate")
    ax.set_title("Manifold World Cup 2026 Markets: Calibration")
    ax.legend(loc="upper left")
    ax.set_aspect("equal")

    fig.tight_layout()
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    fig.savefig(OUT_PATH, dpi=150)
    print(f"Saved to {OUT_PATH}")


if __name__ == "__main__":
    main()
