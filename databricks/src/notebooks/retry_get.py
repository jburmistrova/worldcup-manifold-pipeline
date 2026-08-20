# Databricks notebook source
# Shared retry-with-backoff GET, ported unchanged from ingest/retry_get.py.
# Run via `%run ./retry_get` from ingest_manifold.py and ingest_polymarket.py,
# the direct Databricks-notebook equivalent of that file's plain Python
# import, so the two ingestion notebooks don't each carry their own copy of
# this logic and risk it drifting (same reasoning the original file's own
# docstring gives for why this was extracted in the first place).
#
# Retries on transient 5xx responses, request-level failures (timeouts,
# dropped connections), and two specific 4xx codes found empirically to be
# transient rather than real client errors: 429 (rate limited) and 408
# (request timeout). See ingest/retry_get.py for the full history of how
# each of those was found.
import os
import random
import time

import requests

MAX_RETRIES = int(os.environ.get("MAX_RETRIES", "5"))
RETRYABLE_4XX = {408, 429}


def get_with_retry(url, params=None, timeout=30):
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, params=params, timeout=timeout)
        except requests.exceptions.RequestException:
            if attempt == MAX_RETRIES - 1:
                raise
            time.sleep((2 ** attempt) + random.uniform(0, 1))
            continue

        if resp.status_code < 500 and resp.status_code not in RETRYABLE_4XX:
            resp.raise_for_status()
            return resp.json()
        if attempt == MAX_RETRIES - 1:
            resp.raise_for_status()
        retry_after = resp.headers.get("Retry-After")
        if retry_after is not None:
            time.sleep(float(retry_after) + random.uniform(0, 1))
        else:
            time.sleep((2 ** attempt) + random.uniform(0, 1))
