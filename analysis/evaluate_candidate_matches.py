"""Evaluates both halves of the semantic cross-platform market matcher
(ADR-0014) against real ground truth, not a hand-labeled sample built for
this feature: the outright World Cup winner group already has known-correct
team pairings, implicit in mart_platform_calibration_comparison (the one
hardcoded market pair this whole feature exists to eventually go beyond)
and compare_platform_predictions.py's TEAM_ALIASES-based join. 46 teams
match by exact string equality or a documented alias, and 4 more are
genuine Polymarket-only teams with no correct Manifold match at all
(absorbed into Manifold's "Other" catch-all). The positive 46 test
retrieval/generation precision; the negative 4 test whether either step
produces a false positive when there's nothing correct to find, since
that's the failure mode a human reviewer would actually be hurt by.

Ground-truth counts are derived here at runtime by literally re-running
the same query + normalize() logic compare_platform_predictions.py uses,
not hardcoded as "46" and "4": this project's own established discipline
(ADR-0007/0008/0011) is to confirm real numbers, not assume yesterday's
count is still right. A different printed count here is a signal to
investigate, not a bug in this script.

Every candidate is ranked against the FULL cross-platform universe (all
6,359 Polymarket rows for positives, all ~4,766 Manifold rows for
negatives), not just the 50-row outright-winner subset: the whole point of
this feature is finding a needle in the full haystack, so the eval has to
reflect that difficulty, not an easy closed-world lookup among 50 already-
known candidates.
"""
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import market_embeddings as me
import market_generation as mg

# Same hardcoded IDs mart_platform_calibration_comparison.sql uses, kept in
# sync manually: this script evaluates against that exact market pair, so
# it needs the exact same anchor, not a lookup that could silently drift.
MANIFOLD_OUTRIGHT_MARKET_ID = "JRzL2QcArhM674YSO4d8"
POLYMARKET_OUTRIGHT_MARKET_ID = "0xb5c32a9acd39848acad4913ac4cd49c5de2afcc9d23a8a7ba2419375fab87400"

# Copied from compare_platform_predictions.py, not imported: that script's
# own docstring already justifies this as fine to duplicate at 2 entries
# rather than build a shared alias table for four rows. Same reasoning
# applies here.
TEAM_ALIASES = {
    "Türkiye": "Turkiye",
    "USA 🇺‍🇸 ": "USA",
}


def normalize(team):
    return TEAM_ALIASES.get(team, team)


def main():
    con = me.get_connection()

    manifold_rows = me.fetch_manifold_texts(con)
    polymarket_rows = me.fetch_polymarket_texts(con)

    m_ids = [(mid, aid) for mid, aid, *_ in manifold_rows]
    m_texts = [t for _, _, t, *_ in manifold_rows]
    p_ids = [cid for cid, *_ in polymarket_rows]
    p_texts = [t for _, _, t, *_ in polymarket_rows]

    m_emb = me.compute_or_load_embeddings("manifold", m_ids, m_texts)
    p_emb = me.compute_or_load_embeddings("polymarket", p_ids, p_texts)

    m_index = {ids: i for i, ids in enumerate(m_ids)}
    p_index = {cid: i for i, cid in enumerate(p_ids)}

    # Ground truth, queried directly, same shape as
    # mart_platform_calibration_comparison.sql's own manifold_outcomes /
    # polymarket_outcomes CTEs.
    manifold_teams = con.execute("""
        select a.answer_id, a.answer_text as team
        from stg_manifold_market_answers a
        where a.market_id = ? and coalesce(a.is_other, false) = false
    """, [MANIFOLD_OUTRIGHT_MARKET_ID]).fetchall()
    manifold_by_team = {normalize(team): answer_id for answer_id, team in manifold_teams}

    polymarket_teams = con.execute("""
        select condition_id, answer_text as team
        from stg_polymarket_markets
        where market_id = ? and resolution in ('YES', 'NO')
    """, [POLYMARKET_OUTRIGHT_MARKET_ID]).fetchall()
    polymarket_by_team = {normalize(team): condition_id for condition_id, team in polymarket_teams}

    positive_teams = sorted(set(manifold_by_team) & set(polymarket_by_team))
    negative_teams = sorted(set(polymarket_by_team) - set(manifold_by_team))

    print(f"Ground truth (derived at runtime, not hardcoded):")
    print(f"  {len(manifold_teams)} Manifold outright-winner teams, "
          f"{len(polymarket_teams)} Polymarket outright-winner teams")
    print(f"  {len(positive_teams)} positive pairs (matched teams)")
    print(f"  {len(negative_teams)} negative pairs (Polymarket-only, no correct Manifold match)")
    print()

    # --- Positive teams: retrieval + generation should find the true match ---
    retrieval_hit1 = 0
    retrieval_hit5 = 0
    generation_correct = 0
    positive_top1_scores = []
    misses = []

    for team in positive_teams:
        answer_id = manifold_by_team[team]
        true_condition_id = polymarket_by_team[team]
        m_idx = m_index[(MANIFOLD_OUTRIGHT_MARKET_ID, answer_id)]

        sims = m_emb[m_idx] @ p_emb.T
        ranked = sims.argsort()[::-1]
        true_rank = int((ranked == p_index[true_condition_id]).argmax()) + 1  # 1-based

        top1_score = float(sims[ranked[0]])
        positive_top1_scores.append(top1_score)
        if true_rank == 1:
            retrieval_hit1 += 1
        if true_rank <= 5:
            retrieval_hit5 += 1
        else:
            wrong_idx = ranked[0]
            misses.append((team, p_ids[wrong_idx], p_texts[wrong_idx], true_rank, top1_score))

        top5_idx = ranked[:5]
        candidates = []
        for j in top5_idx:
            condition_id = p_ids[j]
            q, a = [(row[3], row[4]) for row in polymarket_rows if row[0] == condition_id][0]
            candidates.append((q, a, float(sims[j])))

        query_q, query_a = [(row[3], row[4]) for row in manifold_rows
                             if row[0] == MANIFOLD_OUTRIGHT_MARKET_ID and row[1] == answer_id][0]
        result = mg.explain_match(query_q, query_a, candidates)
        picked_condition_id = p_ids[top5_idx[result["pick_index"]]] if result["pick_index"] is not None else None
        if picked_condition_id == true_condition_id:
            generation_correct += 1

    n_pos = len(positive_teams)
    print(f"--- Positive teams (n={n_pos}) ---")
    print(f"Retrieval hit@1: {retrieval_hit1}/{n_pos} ({retrieval_hit1/n_pos:.0%})")
    print(f"Retrieval hit@5 (= recall@5, same arithmetic here since each "
          f"query has exactly one correct answer, not a set): "
          f"{retrieval_hit5}/{n_pos} ({retrieval_hit5/n_pos:.0%})")
    print(f"Generation correct (picked the true match out of its own top-5): "
          f"{generation_correct}/{n_pos} ({generation_correct/n_pos:.0%})")
    print()
    if misses:
        print("Retrieval misses (true match ranked outside top 5), by name:")
        for team, wrong_id, wrong_text, true_rank, top1 in misses:
            print(f"  {team}: top-1 was {wrong_text!r} (score {top1:.3f}), "
                  f"true match ranked #{true_rank}")
        print()

    # --- Negative teams: retrieval/generation should NOT force a match ---
    print(f"--- Negative teams (n={len(negative_teams)}, no correct Manifold match exists) ---")
    negative_best_scores = []
    generation_false_positives = 0
    for team in negative_teams:
        condition_id = polymarket_by_team[team]
        p_idx = p_index[condition_id]

        sims = m_emb @ p_emb[p_idx]
        ranked = sims.argsort()[::-1]
        best_score = float(sims[ranked[0]])
        negative_best_scores.append((team, best_score, m_ids[ranked[0]]))

        top5_idx = ranked[:5]
        candidates = []
        for i in top5_idx:
            mid, aid = m_ids[i]
            q, a = [(row[3], row[4]) for row in manifold_rows if row[0] == mid and row[1] == aid][0]
            candidates.append((q, a, float(sims[i])))

        query_q, query_a = [(row[3], row[4]) for row in polymarket_rows if row[0] == condition_id][0]
        result = mg.explain_match(query_q, query_a, candidates)
        outcome = "FALSE POSITIVE" if result["pick_index"] is not None else "correctly abstained"
        if result["pick_index"] is not None:
            generation_false_positives += 1
        print(f"  {team}: best retrieval score {best_score:.3f}, generation {outcome}")

    print()
    pos_scores_sorted = sorted(positive_top1_scores)
    n = len(pos_scores_sorted)
    pos_median = pos_scores_sorted[n // 2]
    pos_min = pos_scores_sorted[0]
    print(f"Positive top-1 score range: min={pos_min:.3f}, median={pos_median:.3f}")
    neg_scores = [s for _, s, _ in negative_best_scores]
    print(f"Negative best-score range: min={min(neg_scores):.3f}, max={max(neg_scores):.3f}")
    print(f"(Compare these two ranges directly: real separation between "
          f"confident-correct and confident-wrong, or not, is more honest "
          f"than picking one threshold and hiding the ambiguity.)")
    print()
    print(f"Generation false positives on negative teams: "
          f"{generation_false_positives}/{len(negative_teams)}")


if __name__ == "__main__":
    main()
