"""Retrieval-only discovery step for semantic cross-platform market
matching (ADR-0014): the actual point of this feature. mart_platform_calibration_comparison
only ever compares the one hand-picked outright-winner market pair; this
runs every Manifold market/answer against the full 6,359-row Polymarket
universe to surface candidate pairs nobody has hand-picked, for a human to
review. It does not decide anything: no candidate here is trusted, no
mart is touched, that's explicit_top_candidate_matches.py's and a
human's job, not this script's.

Retrieval only, no LLM calls: a single (n_manifold, 384) x (384,
n_polymarket) matrix multiply is well under a second even at this scale
(see market_embeddings.top_k_similar), so there's no reason to bound this
script's scope the way the generation step has to be bounded.
"""
import sys
import time

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import market_embeddings as me

K = 5
OUTPUT_PATH = f"{me.REPO_ROOT}/data/processed/candidate_market_matches.csv"


def main():
    con = me.get_connection()
    manifold_rows = me.fetch_manifold_texts(con)
    polymarket_rows = me.fetch_polymarket_texts(con)
    print(f"{len(manifold_rows)} Manifold market/answer rows, "
          f"{len(polymarket_rows)} Polymarket market rows")

    m_ids = [(mid, aid) for mid, aid, *_ in manifold_rows]
    m_texts = [embed_text for _, _, embed_text, *_ in manifold_rows]
    p_ids = [cid for cid, *_ in polymarket_rows]
    p_texts = [embed_text for _, _, embed_text, *_ in polymarket_rows]

    m_emb = me.compute_or_load_embeddings("manifold", m_ids, m_texts)
    p_emb = me.compute_or_load_embeddings("polymarket", p_ids, p_texts)

    t0 = time.time()
    top_idx, top_scores = me.top_k_similar(m_emb, p_emb, k=K)
    print(f"retrieval: {time.time() - t0:.2f}s for {len(manifold_rows)} x {len(polymarket_rows)}")

    header = [
        "manifold_market_id", "manifold_answer_id", "manifold_text",
        "rank",
        "polymarket_condition_id", "polymarket_market_id", "polymarket_text",
        "cosine_similarity",
    ]
    rows = []
    top1_scores = []
    for i, (market_id, answer_id, embed_text, *_ ) in enumerate(manifold_rows):
        for rank, (j, score) in enumerate(zip(top_idx[i], top_scores[i]), start=1):
            condition_id, canonical_market_id, poly_text, *_ = polymarket_rows[j]
            rows.append([
                market_id, answer_id or "", embed_text,
                rank,
                condition_id, canonical_market_id, poly_text,
                round(float(score), 4),
            ])
            if rank == 1:
                top1_scores.append(float(score))

    me.write_csv(OUTPUT_PATH, header, rows)
    print(f"wrote {len(rows)} rows ({len(manifold_rows)} manifold rows x top-{K}) to {OUTPUT_PATH}")

    top1_scores.sort(reverse=True)
    n = len(top1_scores)
    print()
    print("Top-1 similarity score distribution across all Manifold rows:")
    print(f"  max:    {top1_scores[0]:.4f}")
    print(f"  p90:    {top1_scores[int(n * 0.10)]:.4f}")
    print(f"  median: {top1_scores[n // 2]:.4f}")
    print(f"  p10:    {top1_scores[int(n * 0.90)]:.4f}")
    print(f"  min:    {top1_scores[-1]:.4f}")

    print()
    print("Top 20 highest-confidence candidate pairs (rank 1 only):")
    rank1 = sorted(
        (r for r in rows if r[3] == 1),
        key=lambda r: -r[-1],
    )[:20]
    for r in rank1:
        print(f"  {r[7]:.4f}  {r[2]!r:<45} <-> {r[6]!r}")


if __name__ == "__main__":
    main()
