#!/usr/bin/env bash
# The container's entrypoint. Runs the exact same steps as README's "How to
# run it", in order, inside the pod. `set -e` means any real failure (a
# non-zero exit from any command) stops the script and exits non-zero, which
# is what lets the Kubernetes Job's backoffLimit retry logic actually work.
# A script that swallowed errors and kept going would look like a completed
# Job even after a real failure.
set -euo pipefail

echo "=== Ingest: markets ==="
python ingest/pull_markets.py

echo "=== Ingest: market answers ==="
python ingest/pull_market_answers.py

echo "=== Ingest: bets ==="
python ingest/pull_bets.py

echo "=== Spark: flatten raw JSON to Parquet ==="
python spark/flatten_to_parquet.py

echo "=== dbt: build + test (staging -> intermediate -> marts) ==="
cd dbt
dbt build --profiles-dir .
cd ..

echo "=== Analysis: calibration chart + Brier/liquidity metrics ==="
python analysis/plot_calibration.py
python analysis/compute_calibration_metrics.py

echo "=== Pipeline complete ==="
