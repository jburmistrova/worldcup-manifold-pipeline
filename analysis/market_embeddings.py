"""Shared retrieval module for semantic cross-platform market matching
(ADR-0014). A deliberate exception to this project's usual rule that every
analysis/*.py script stands alone: embedding computation, caching, and
top-k retrieval are real algorithmic logic that find_candidate_market_matches.py,
explain_top_candidate_matches.py, and evaluate_candidate_matches.py all need
to run identically, or the evaluation numbers stop describing what discovery
actually produced. Same "worth extracting once it's not just a 2-line dict"
judgment this project already made for dbt/macros/prob_bucket.sql.

Requires sentence-transformers (requirements-semantic-matching.txt), NOT
installed by the base requirements.txt or by CI. Import it lazily inside
compute_or_load_embeddings, only on a cache miss, so a cache-hit run (the
common case once embeddings exist) never pays torch's real import/init cost.

Must run against the native arm64 Homebrew Python
(/opt/homebrew/opt/python@3.14), not /usr/local's Intel build: torch
publishes no usable wheel for the Intel path, confirmed empirically while
building this feature (see requirements.md). This module doesn't check
that itself; a wrong Python just fails the sentence_transformers import
with a normal error at install time, not something worth defending against
at runtime.
"""
import csv
import hashlib
import json
import os

import duckdb
import numpy as np

# Anchored at this file's location, not the process's cwd at invocation
# time: every other analysis/*.py script assumes "run from the repo root"
# and gets away with a bare relative DB_PATH, but this module is the first
# to query staging views (stg_manifold_markets etc.) directly rather than
# only already-materialized mart tables. Staging views were built with
# dbt-duckdb's external_location meta (_sources.yml's
# "../data/processed/{name}/*.parquet"), and DuckDB re-resolves that
# relative pattern against the process's CURRENT working directory at every
# single query, not once at connection time or against the database file's
# own location, confirmed empirically: a query succeeds right after
# os.chdir("dbt") and fails again the moment cwd changes back, even on the
# same open connection. Absolute paths here sidestep the whole class of
# "works from repo root, breaks from anywhere else" bug this would
# otherwise be.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DBT_DIR = os.path.join(REPO_ROOT, "dbt")
DB_PATH = os.path.join(DBT_DIR, "manifold.duckdb")
MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_CACHE_DIR = os.path.join(REPO_ROOT, "data/processed/embeddings")


def get_connection(read_only=True):
    # Left chdir'd into dbt/ for the rest of the process's life, matching
    # where `dbt build` itself always runs from and where every staging
    # view's relative Parquet pattern actually resolves. Safe here because
    # every other path this module and its callers touch (EMBEDDING_CACHE_DIR,
    # and any output CSV path a caller builds) is absolute, anchored at
    # REPO_ROOT above, not relative to whatever the caller's cwd happened
    # to be at import time.
    os.chdir(DBT_DIR)
    return duckdb.connect(os.path.basename(DB_PATH), read_only=read_only)


def fetch_manifold_texts(con):
    """(market_id, answer_id, embed_text, question, answer_text) for every
    Manifold market/answer worth embedding. is_other is excluded:
    Manifold's synthetic "Other" catch-all answer has no real-world
    referent to match against, already correctly excluded from the
    per-team comparison in compare_platform_predictions.py.

    embed_text is question + answer_text combined ("Will Spain win the
    2026 FIFA World Cup? [Spain]"), NOT the bare team name alone. This is
    a reversal of this function's first version, corrected after a real
    bug, not a stylistic preference. Bare team names were tried first, on
    the theory that concatenating a long, near-identical question onto
    every one of a market's ~50 answers would dilute the one signal that
    distinguishes them (the team). True within one market's answers, but
    wrong at full-corpus scale: a single team appears in dozens of
    differently-typed markets across this dataset (Spain to win outright,
    Spain to finish 3rd, Spain to reach the final, ...), and every one of
    them reduces to the identical bare string "Spain", giving them
    literally tied (cosine similarity 1.0) embeddings. Retrieval against
    the bare-name embeddings couldn't distinguish market TYPE at all,
    confirmed by running the real pipeline: find_candidate_market_matches.py's
    top-5 for the actual outright-winner queries turned out to be an
    arbitrary tied subset of same-team markets, not ranked by real
    relevance, and explain_top_candidate_matches.py's LLM correctly
    noticed none of its 5 arbitrary candidates said "win outright" and
    abstained, for teams where a real matching market plainly exists.
    Confirmed the fix directly before trusting it: embedding
    "Will Spain win the World Cup? [Spain]" against "Will Spain finish 3rd?
    [Spain]" and "Will Portugal win the World Cup? [Portugal]" scores 0.903
    and 0.757 respectively, both correctly below the 0.857 a true
    same-team-same-type match gets against a differently-worded version of
    the same question, real separation on both the team and the
    market-type axis, not a tie.
    """
    rows = con.execute("""
        select
            m.market_id,
            a.answer_id,
            case
                when a.answer_text is null then m.question
                else m.question || ' [' || a.answer_text || ']'
            end as embed_text,
            m.question,
            a.answer_text
        from stg_manifold_markets m
        left join stg_manifold_market_answers a
            on m.market_id = a.market_id and coalesce(a.is_other, false) = false
        where coalesce(a.is_other, false) = false
    """).fetchall()
    return rows


def fetch_polymarket_texts(con):
    """(condition_id, canonical_market_id, embed_text, question,
    answer_text) for every Polymarket market. condition_id is the real
    join key (unique per binary market, unaffected by negRisk grouping);
    canonical_market_id is the grouped market_id, kept alongside for
    readability in output CSVs.

    Same embed_text construction as fetch_manifold_texts, for the same
    reason (see that function's docstring): question + answer_text
    combined, not the bare team name alone, needed to distinguish
    different market TYPES about the same team, not just different teams.
    Polymarket's own question is often already team-specific ("Will Spain
    win the World Cup?", not a generic shared question the way Manifold's
    is), which makes the bug this fixes even more visible on this side:
    every one of Spain's ~35 separate Polymarket markets (outright winner,
    group stage, top scorer, exact-date props, ...) has answer_text =
    "Spain" and would otherwise embed identically regardless of what each
    market actually asks.

    Raises a clear error rather than returning an empty result if
    stg_polymarket_markets is empty, i.e. INCLUDE_POLYMARKET=true dbt build
    hasn't been run, the same failure mode mart_platform_calibration_comparison
    already has, just surfaced with an actionable message instead of a
    silent empty CSV three steps later.
    """
    rows = con.execute("""
        select
            condition_id,
            market_id as canonical_market_id,
            case
                when answer_text is null then question
                else question || ' [' || answer_text || ']'
            end as embed_text,
            question,
            answer_text
        from stg_polymarket_markets
    """).fetchall()
    if not rows:
        raise SystemExit(
            "stg_polymarket_markets is empty. Run "
            "`cd dbt && INCLUDE_POLYMARKET=true dbt build --profiles-dir .` "
            "first (see README.md's Polymarket section)."
        )
    return rows


def _content_hash(ids, texts):
    # Deterministic given (model, ids, texts): hashing the sorted pairs, not
    # insertion order, so a query that happens to return rows in a
    # different order doesn't spuriously invalidate a cache that's still
    # semantically identical.
    h = hashlib.sha256()
    h.update(MODEL_NAME.encode())
    for i, t in sorted(zip(ids, texts)):
        h.update(str(i).encode())
        h.update(b"\x00")
        h.update(t.encode())
        h.update(b"\x01")
    return h.hexdigest()


def compute_or_load_embeddings(platform, ids, texts):
    """Returns an (N, 384) float32 array, L2-normalized so a plain dot
    product equals cosine similarity. Cached to disk under
    EMBEDDING_CACHE_DIR keyed by a content hash of (model, ids, texts):
    embeddings are deterministic for a given model + text, so re-running a
    script twice in a row shouldn't pay to re-embed thousands of rows
    (import torch, load the model, run inference) when nothing changed.
    """
    os.makedirs(EMBEDDING_CACHE_DIR, exist_ok=True)
    npz_path = f"{EMBEDDING_CACHE_DIR}/{platform}_embeddings.npz"
    meta_path = f"{EMBEDDING_CACHE_DIR}/{platform}_embeddings.meta.json"

    current_hash = _content_hash(ids, texts)

    if os.path.exists(npz_path) and os.path.exists(meta_path):
        with open(meta_path) as f:
            meta = json.load(f)
        if meta.get("content_hash") == current_hash and meta.get("model") == MODEL_NAME:
            print(f"[{platform}] embedding cache hit ({meta['n_rows']} rows, no re-embedding)")
            return np.load(npz_path)["embeddings"]

    print(f"[{platform}] embedding cache miss, computing {len(texts)} embeddings...")
    from sentence_transformers import SentenceTransformer  # lazy: only on a real cache miss

    model = SentenceTransformer(MODEL_NAME)
    embeddings = model.encode(
        texts, batch_size=64, show_progress_bar=True, convert_to_numpy=True
    ).astype(np.float32)
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    embeddings = embeddings / norms

    np.savez(npz_path, embeddings=embeddings)
    with open(meta_path, "w") as f:
        json.dump({"model": MODEL_NAME, "content_hash": current_hash, "n_rows": len(texts)}, f)

    return embeddings


def top_k_similar(query_vectors, candidate_vectors, k=5):
    """Brute-force cosine similarity: at ~7,000 total rows this is a single
    (n_query, 384) x (384, n_candidate) matmul, well under a second, no
    reason for a vector DB or DuckDB's VSS extension at this scale (see
    ADR-0002 / docs/project_scale_vs_production.md). Returns
    (top_k_indices, top_k_scores), both shape (n_query, k), scores sorted
    descending within each row.
    """
    sims = query_vectors @ candidate_vectors.T  # (n_query, n_candidate); already cosine, both L2-normalized
    k = min(k, sims.shape[1])
    part = np.argpartition(-sims, k - 1, axis=1)[:, :k]
    row_idx = np.arange(sims.shape[0])[:, None]
    part_scores = sims[row_idx, part]
    order = np.argsort(-part_scores, axis=1)
    top_k_indices = part[row_idx, order]
    top_k_scores = part_scores[row_idx, order]
    return top_k_indices, top_k_scores


def write_csv(path, header, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)
