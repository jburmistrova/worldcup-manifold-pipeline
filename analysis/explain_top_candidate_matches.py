"""Generation step for semantic cross-platform market matching (ADR-0014):
the actual human-reviewable deliverable this feature exists to produce.
Reads find_candidate_market_matches.py's output CSV (pure retrieval, no
LLM involved) and runs market_generation.explain_match over the top-N
highest-confidence Manifold rows by their rank-1 retrieval score, asking a
local LLM to pick the genuinely correct candidate among the top-5 (or say
none of them are), with reasoning.

Bounded to the top N rows, not the full ~4,766-row corpus: retrieval is
one cheap matrix multiply (see find_candidate_market_matches.py), but each
generation call is a real, seconds-long local LLM inference. Running it
over every row would take hours for no proportionate gain, since the
highest-value review targets are the highest-confidence retrieval hits
anyway, exactly what N controls. See evaluate_candidate_matches.py for the
separate, smaller, ground-truth-backed evaluation of both halves together.
"""
import csv
import sys
import time
from collections import defaultdict

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import market_embeddings as me
import market_generation as mg

N = 100
INPUT_PATH = f"{me.REPO_ROOT}/data/processed/candidate_market_matches.csv"
OUTPUT_PATH = f"{me.REPO_ROOT}/data/processed/candidate_market_matches_explained.csv"


def load_candidate_groups():
    groups = defaultdict(list)
    with open(INPUT_PATH, newline="") as f:
        for row in csv.DictReader(f):
            key = (row["manifold_market_id"], row["manifold_answer_id"])
            groups[key].append(row)
    for key in groups:
        groups[key].sort(key=lambda r: int(r["rank"]))
    return groups


def main():
    groups = load_candidate_groups()
    print(f"{len(groups)} distinct Manifold market/answer rows in {INPUT_PATH}")

    ranked = sorted(
        groups.items(),
        key=lambda kv: -float(kv[1][0]["cosine_similarity"]),
    )[:N]
    print(f"explaining the top {len(ranked)} by rank-1 similarity score")

    con = me.get_connection()
    manifold_lookup = {
        (market_id, answer_id or None): (question, answer_text)
        for market_id, answer_id, embed_text, question, answer_text in me.fetch_manifold_texts(con)
    }
    polymarket_lookup = {
        condition_id: (question, answer_text)
        for condition_id, canonical_market_id, embed_text, question, answer_text in me.fetch_polymarket_texts(con)
    }

    header = [
        "manifold_market_id", "manifold_answer_id", "manifold_text",
        "llm_pick_rank", "llm_pick_polymarket_condition_id", "llm_pick_polymarket_text",
        "llm_pick_similarity", "llm_reasoning",
    ]
    out_rows = []
    t_start = time.time()
    for i, ((market_id, answer_id), candidate_rows) in enumerate(ranked, start=1):
        query_question, query_answer_text = manifold_lookup[(market_id, answer_id or None)]
        candidates = []
        for r in candidate_rows:
            p_question, p_answer_text = polymarket_lookup[r["polymarket_condition_id"]]
            candidates.append((p_question, p_answer_text, float(r["cosine_similarity"])))

        result = mg.explain_match(query_question, query_answer_text, candidates)
        pick = result["pick_index"]
        if pick is not None:
            picked_row = candidate_rows[pick]
            out_rows.append([
                market_id, answer_id, candidate_rows[0]["manifold_text"],
                pick + 1, picked_row["polymarket_condition_id"], picked_row["polymarket_text"],
                picked_row["cosine_similarity"], result["reasoning"].replace("\n", " "),
            ])
        else:
            out_rows.append([
                market_id, answer_id, candidate_rows[0]["manifold_text"],
                "", "", "", "", result["reasoning"].replace("\n", " "),
            ])

        if i % 10 == 0:
            elapsed = time.time() - t_start
            print(f"  {i}/{len(ranked)} done, {elapsed:.0f}s elapsed, "
                  f"~{elapsed / i * (len(ranked) - i):.0f}s remaining")

    me.write_csv(OUTPUT_PATH, header, out_rows)
    print(f"wrote {len(out_rows)} rows to {OUTPUT_PATH}")

    n_picked = sum(1 for r in out_rows if r[3] != "")
    print(f"model picked a candidate for {n_picked}/{len(out_rows)}, "
          f"said none matched for {len(out_rows) - n_picked}/{len(out_rows)}")


if __name__ == "__main__":
    main()
