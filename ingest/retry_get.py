"""Shared retry-with-backoff GET, used by all three ingest scripts.

Extracted here because all three needed the exact same behavior, not because
it seemed like good practice in the abstract: pull_bets.py had this logic
inline first (after a real 503 crashed a run on 2026-07-31), then
pull_markets.py and pull_market_answers.py hit their own real failures
without it. Copy-pasting a third time would leave the same retry semantics
drifting across three files with no reason for them to differ.

Retries on both transient 5xx responses and on request-level failures
(timeouts, dropped connections) that raise before any response exists to
check a status code on -- both are transient in the same sense (retrying is
likely to work), so both get identical backoff treatment. 4xx errors are
never retried -- a client error won't fix itself by waiting.

The timeout failures this was actually needed for turned out not to be a
Docker networking artifact, even though that was the first, plausible-looking
guess -- confirmed by re-running the same request directly from the host,
outside any container, and getting the same 17-29 second response times.
Manifold's /v0/search-markets is genuinely slow (or throttled) under rapid
repeated calls; the fix is the same either way (retry + a realistic timeout),
but the cause is worth being able to state correctly, not just guessed at.
"""
import os
import random
import time

import requests

MAX_RETRIES = int(os.environ.get("MAX_RETRIES", "5"))


def get_with_retry(url, params=None, timeout=30):
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, params=params, timeout=timeout)
        except requests.exceptions.RequestException:
            # the request itself failed before producing a response - same
            # retry treatment as a 5xx below, just no status code involved
            if attempt == MAX_RETRIES - 1:
                raise
            time.sleep((2 ** attempt) + random.uniform(0, 1))
            continue

        # < 500 covers both success (2xx, just return it) and client errors
        # (4xx) - raise_for_status() only actually raises on the 4xx case,
        # a 2xx passes through and .json() returns normally
        if resp.status_code < 500:
            resp.raise_for_status()
            return resp.json()
        # got a 5xx. on the last allowed attempt, stop retrying and surface
        # the real error instead of silently giving up
        if attempt == MAX_RETRIES - 1:
            resp.raise_for_status()
        # 2**attempt: 1, 2, 4, 8, 16 seconds - growing gap between retries,
        # plus up to 1s of random jitter so retries don't all land at once
        time.sleep((2 ** attempt) + random.uniform(0, 1))
