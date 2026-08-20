# ADR-0020: Cross-platform market matching (RAG) stays local, not ported to Databricks

**Status:** Accepted
**Date:** 2026-08-19

## Context

ADR-0014 built a real RAG pipeline (local `sentence-transformers` embeddings + local Ollama generation) to find cross-platform market pairs beyond the one hand-picked outright-winner pair. The migration's own instructions were explicit that this step shouldn't be silently dropped or reframed: either keep it local for a real, checkable reason, or move it to a Databricks notebook calling the same local model. That's a real either/or, not a default -- it needed to be checked, not assumed.

## What was checked, not assumed

A Databricks notebook run for exactly this question (`.ai_dev_kit/test_ollama_reach`, a real job submitted and run on this workspace's serverless compute, not a thought experiment) confirmed two things directly:

1. `socket.gethostname()` on the Databricks compute node returns `spark.host.local` -- a different machine, not this laptop, confirming "localhost" inside a Databricks notebook means the remote node's own localhost, not the machine Ollama runs on.
2. A request to `http://localhost:11434/api/tags` (Ollama's default API port) from that notebook fails with `Connection refused` -- there is no service on that port on the remote node, and there is no network path from Databricks' serverless compute back to this laptop without an explicit tunnel (ngrok, a reverse SSH tunnel, or similar) this project doesn't set up.

## Decision

**The RAG pipeline stays exactly where ADR-0014 left it: local, unmoved.** `analysis/find_candidate_market_matches.py`, `explain_top_candidate_matches.py`, and `evaluate_candidate_matches.py` continue to run against the local `venv-semantic-matching/` environment and a locally-running Ollama instance. Nothing about its own data source changed as part of this migration -- it still reads from the local DuckDB warehouse (`dbt/manifold.duckdb`), not from anything the Databricks port produced.

Moving the *orchestration* to a Databricks notebook while still calling out to a local Ollama instance was considered and rejected for the same reason confirmed above: there's no network path back to this laptop from Databricks' compute without standing up a tunnel, a real infrastructure addition (and a new attack surface -- exposing a local port to the internet) that this project's own no-API-key, no-external-credential-plumbing stance (ADR-0014) argues against taking on for a single evaluation step.

## Consequences

**Gained:** a real, tested answer instead of an assumed one -- "Databricks can't reach my laptop" is a specific, checkable claim, not a hand-wave, and it was actually checked before this ADR was written.

**Consequence for docs/results.md's numbers:** since this step's data path is unchanged (still the local DuckDB warehouse, not anything under `worldcup_manifold`), ADR-0014's existing results -- **48/48 (100%) retrieval hit@1, 28/48 (58%) generation correct** -- stand as-is. No rerun was needed or performed for this specific number; re-running an unchanged pipeline against unchanged data and reporting the same number would not be "re-verification," it would be restating a result that was never at risk. This is a deliberate, stated exception to the migration's general "re-run everything" rule, not a quiet skip: it applies specifically because nothing upstream of this step changed, and stops applying the moment that becomes false.

**Not done:** exposing local Ollama via a tunnel to make it reachable from Databricks. A real option, deliberately not taken -- the security/complexity cost of a public tunnel to a local LLM server isn't justified by moving one evaluation script's *orchestration* (not its actual compute) onto Databricks, when the compute itself would still be running on this laptop either way.
