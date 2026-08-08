"""Bootstrap significance test: is Manifold (play-money) meaningfully
worse-calibrated than Polymarket (real-money) on the same real-world event
(the World Cup outright winner), at a comparable pre-tournament snapshot?

Explicitly a data-science-flavored exception for this one question, not the
project's usual approach (see ADR-0013): an earlier bootstrap significance
test, for a different comparison, was built and then deliberately removed
from this project as out of scope for a data engineering portfolio piece.
Revisited here only because the user asked directly for a statistical
answer to a specific hypothesis, with the sample-size caveat below reported
plainly rather than glossed over.

Small, unbalanced sample, by construction, not an oversight: 47 Manifold
predictions, 50 Polymarket predictions, exactly one true positive (Spain)
per platform. Resampling with replacement from a sample this size, this
imbalanced, can occasionally draw zero positives in a single bootstrap
iteration; that's expected, not a bug, and part of why the resulting
confidence interval is wide.
"""
import duckdb
import numpy as np

DB_PATH = "dbt/manifold.duckdb"
N_BOOTSTRAP = 10_000
SEED = 42


def brier(predicted, actual):
    return np.mean((predicted - actual) ** 2)


def main():
    con = duckdb.connect(DB_PATH, read_only=True)
    rows = con.execute("""
        select source_platform, predicted_prob, cast(is_yes as double) as is_yes
        from mart_platform_calibration_comparison
    """).fetchall()

    manifold = np.array([(p, y) for plat, p, y in rows if plat == "manifold"])
    polymarket = np.array([(p, y) for plat, p, y in rows if plat == "polymarket"])

    n_manifold, n_polymarket = len(manifold), len(polymarket)
    brier_manifold = brier(manifold[:, 0], manifold[:, 1])
    brier_polymarket = brier(polymarket[:, 0], polymarket[:, 1])
    observed_diff = brier_manifold - brier_polymarket

    print(f"Manifold:   n={n_manifold}, Brier={brier_manifold:.4f}")
    print(f"Polymarket: n={n_polymarket}, Brier={brier_polymarket:.4f}")
    print(f"Observed difference (Manifold - Polymarket): {observed_diff:.4f}")
    print(f"Positive direction = Manifold worse-calibrated (higher Brier is worse).")
    print()

    # bootstrap: resample each platform's own sample independently, with
    # replacement, at its own real size, preserving the group structure
    # rather than pooling. Each iteration recomputes both Brier scores and
    # their difference, building an empirical distribution for the
    # difference under real resampling variability.
    rng = np.random.default_rng(SEED)
    diffs = np.empty(N_BOOTSTRAP)
    for i in range(N_BOOTSTRAP):
        m_sample = manifold[rng.integers(0, n_manifold, n_manifold)]
        p_sample = polymarket[rng.integers(0, n_polymarket, n_polymarket)]
        diffs[i] = brier(m_sample[:, 0], m_sample[:, 1]) - brier(p_sample[:, 0], p_sample[:, 1])

    ci_low, ci_high = np.percentile(diffs, [2.5, 97.5])
    # two-sided bootstrap p-value: proportion of resamples on the opposite
    # side of zero from the observed difference, doubled
    if observed_diff >= 0:
        p_value = 2 * np.mean(diffs <= 0)
    else:
        p_value = 2 * np.mean(diffs >= 0)
    p_value = min(p_value, 1.0)

    print(f"95% bootstrap CI for the difference: [{ci_low:.4f}, {ci_high:.4f}]")
    print(f"Approximate two-sided bootstrap p-value: {p_value:.3f}")
    print(f"Zero inside the CI: {ci_low <= 0 <= ci_high}")
    print()
    print("Conclusion: " + (
        "the CI excludes zero, a statistically significant difference at the ~5% level."
        if not (ci_low <= 0 <= ci_high)
        else "the CI includes zero, no statistically significant difference detected at this sample size."
    ))


if __name__ == "__main__":
    main()
