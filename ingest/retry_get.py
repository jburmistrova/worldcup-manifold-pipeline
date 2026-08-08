"""Shared retry-with-backoff GET, used by all three ingest scripts.

Extracted here because all three needed the exact same behavior, not because
it seemed like good practice in the abstract: pull_bets.py had this logic
inline first (after a real 503 crashed a run on 2026-07-31), then
pull_markets.py and pull_market_answers.py hit their own real failures
without it. Copy-pasting a third time would leave the same retry semantics
drifting across three files with no reason for them to differ.

Retries on transient 5xx responses, on request-level failures (timeouts,
dropped connections) that raise before any response exists to check a
status code on, and on two specific 4xx codes: 429 (rate limited) and 408
(request timeout). All get identical backoff treatment: all are transient
in the same sense, retrying is likely to work. Every other 4xx is never
retried. A genuine client error (a bad param, a missing resource) won't fix
itself by waiting.

Both 429 and 408 were found empirically pulling Polymarket data at real
scale (ADR-0011, ADR-0012), not assumed from the spec, in two separate
passes: 429 showed up on a 60-market sample, 408 only appeared 1,125
markets into a 6,358-market run, load the small sample never reached. A
naive "never retry 4xx" rule would have needed a third pass to catch each
new exception one at a time; the actual lesson is that any 4xx meaning
"this failed for reasons unrelated to what I sent" (rate limiting, a
server-side timeout) belongs in the same retryable bucket as a 5xx, not
that these two specific codes are the complete list.

The timeout failures this was actually needed for turned out not to be a
Docker networking artifact, even though that was the first, plausible-looking
guess. Confirmed by re-running the same request directly from the host,
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
# 4xx codes that mean "transient, try again" rather than "you sent something
# wrong": rate limiting and server-side timeouts, not an exhaustive list of
# every possible transient 4xx, just the two found empirically so far.
RETRYABLE_4XX = {408, 429}


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

        # < 500 and not a known-transient 4xx covers success (2xx, just
        # return it) and real client errors - raise_for_status() only
        # actually raises on the error case, a 2xx passes through and
        # .json() returns normally
        if resp.status_code < 500 and resp.status_code not in RETRYABLE_4XX:
            resp.raise_for_status()
            return resp.json()
        # got a 5xx or a retryable 4xx. on the last allowed attempt, stop
        # retrying and surface the real error instead of silently giving up
        if attempt == MAX_RETRIES - 1:
            resp.raise_for_status()
        # respect Retry-After when the server gives one (common on 429s);
        # otherwise fall back to the same exponential backoff as a 5xx
        retry_after = resp.headers.get("Retry-After")
        if retry_after is not None:
            time.sleep(float(retry_after) + random.uniform(0, 1))
        else:
            # 2**attempt: 1, 2, 4, 8, 16 seconds - growing gap between
            # retries, plus up to 1s of random jitter so retries don't all
            # land at once
            time.sleep((2 ** attempt) + random.uniform(0, 1))
