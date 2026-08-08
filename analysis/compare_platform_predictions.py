"""Descriptive comparison of Manifold vs. Polymarket's pre-tournament
implied probabilities, team by team. No significance test here, on
purpose: this answers "how much did the two platforms agree," not "is any
disagreement real," a genuinely different, DE-appropriate question (see
docs/results.md's platform-comparison addendum for the significance test
this deliberately isn't).

Team names need light normalization to join across platforms: Manifold's
"Türkiye" vs. Polymarket's "Turkiye", and a flag-emoji artifact on
Manifold's "USA" entry. Same class of cross-platform naming mismatch
ADR-0008 handled with team_aliases.csv, small enough here to keep inline
rather than build a second alias table for four rows.

Five teams are genuinely one-platform-only, not a matching bug: Manifold's
outright market has an "Other" catch-all answer absorbing longshots
individually listed by Polymarket (Bosnia-Herzegovina, Peru, Qatar, Saudi
Arabia). Correctly excluded from a per-team comparison, not guessed at.
"""
import duckdb

DB_PATH = "dbt/manifold.duckdb"

TEAM_ALIASES = {
    "Türkiye": "Turkiye",
    "USA 🇺‍🇸 ": "USA",
}


def normalize(team):
    return TEAM_ALIASES.get(team, team)


def main():
    con = duckdb.connect(DB_PATH, read_only=True)
    rows = con.execute("""
        select source_platform, team, predicted_prob
        from mart_platform_calibration_comparison
    """).fetchall()

    manifold = {normalize(t): p for plat, t, p in rows if plat == "manifold"}
    polymarket = {normalize(t): p for plat, t, p in rows if plat == "polymarket"}

    common_teams = sorted(set(manifold) & set(polymarket))
    manifold_only = sorted(set(manifold) - set(polymarket))
    polymarket_only = sorted(set(polymarket) - set(manifold))

    print(f"Teams on both platforms: {len(common_teams)}")
    print(f"Manifold-only (no Polymarket match): {manifold_only}")
    print(f"Polymarket-only (no Manifold match): {polymarket_only}")
    print()

    comparisons = []
    for team in common_teams:
        m, p = manifold[team], polymarket[team]
        comparisons.append((team, m, p, abs(m - p)))

    comparisons.sort(key=lambda x: -x[3])

    print(f"{'Team':<20} {'Manifold':>10} {'Polymarket':>12} {'Abs diff':>10}")
    for team, m, p, diff in comparisons:
        print(f"{team:<20} {m:>10.4f} {p:>12.4f} {diff:>10.4f}")

    diffs = [c[3] for c in comparisons]
    diffs_sorted = sorted(diffs)
    n = len(diffs_sorted)
    median = diffs_sorted[n // 2] if n % 2 else (diffs_sorted[n // 2 - 1] + diffs_sorted[n // 2]) / 2

    print()
    print(f"n={n}")
    print(f"Mean absolute difference: {sum(diffs)/n:.4f}")
    print(f"Median absolute difference: {median:.4f}")
    print(f"Max absolute difference: {max(diffs):.4f} ({comparisons[0][0]})")
    print(f"Min absolute difference: {min(diffs):.4f} ({comparisons[-1][0]})")
    print()

    for threshold in [0.01, 0.02, 0.05]:
        close = sum(1 for d in diffs if d <= threshold)
        print(f"Within {threshold:.0%}: {close}/{n} teams ({close/n:.0%})")


if __name__ == "__main__":
    main()
