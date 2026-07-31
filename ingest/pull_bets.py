"""Full bet (trade) history for every market, as raw JSON Lines.

Pulls everything /v0/bets returns, unfiltered — including cancelled limit
orders and share redemptions, which are not real price-moving trades. That
filtering is a business-logic decision (what counts as a "real" trade), so
per ADR-0005 it belongs in dbt's staging model (stg_manifold_bets), not here.
This script's job is extract + load only. Full raw payload per bet, no field
selection — same reasoning as pull_markets.py and pull_market_answers.py.
"""
import json
import random
import time

import requests

BASE_URL = "https://api.manifold.markets/v0"
MARKETS_PATH = "data/raw/worldcup_2026_markets.jsonl"
OUTPUT_PATH = "data/raw/worldcup_2026_bets.jsonl"
PAGE_LIMIT = 1000
MAX_RETRIES = 5


def get_bets_page(contract_id, after=None):
    # fetches ONE page of bets - the actual pagination loop lives in get_all_bets below
    # there IS a limit here (PAGE_LIMIT=1000) - what's different from pull_markets.py
    # is `after` (a cursor) instead of `offset` (a raw count), see get_all_bets for why that matters
    params = {"contractId": contract_id, "limit": PAGE_LIMIT, "order": "asc"}
    if after:
        params["after"] = after

    # retry with exponential backoff + jitter on transient server errors (5xx)
    # only - not hypothetical, hit a real 503 mid-run on 2026-07-31 that
    # crashed the whole script after 125 of 621 markets, losing all progress.
    # per [1] AWS's Exponential Backoff and Jitter, already cited in
    # docs/data_engineering_best_practices.md but not actually built until now.
    # 4xx errors are NOT retried - a client error won't fix itself by waiting.
    for attempt in range(MAX_RETRIES):
        resp = requests.get(f"{BASE_URL}/bets", params=params, timeout=15)
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
        wait = (2 ** attempt) + random.uniform(0, 1)
        time.sleep(wait)


def get_all_bets(contract_id):
    """`after` is a cursor anchored to a specific bet's id ("give me everything
    after THIS bet"), not a raw count like offset was - so ranking ties can't
    shift it the way they did for markets pagination. Confirmed empirically
    too, not just in theory: zero duplicate bet ids across all 400,207 bets.
    """
    # start with empty bets
    bets = []
    # `after` is the cursor described above - NOT a running total or counter.
    # starts as None (no cursor yet = give us the first page), then becomes
    # the last bet's id after each page, so the next call picks up right after it
    after = None

    # continue until we get everything
    while True:
        # first call has after=None (first page); later calls are anchored to the last bet's id
        page = get_bets_page(contract_id, after=after)
        if not page:
            break
        bets.extend(page)
        if len(page) < PAGE_LIMIT:
            break
        after = page[-1]["id"]
        time.sleep(0.15)
    return bets


def load_market_ids():
    # get market_ids from our pull_markets.py output
    market_ids = []
    with open(MARKETS_PATH) as f:
        for line in f:
            market_ids.append(json.loads(line)["id"])
    return market_ids


def main():
    # get market ids first so we have something to pull bets from
    market_ids = load_market_ids()
    print(f"Fetching bet history for {len(market_ids)} markets")

    # set to zero at start
    total_bets = 0

    # with our output path
    with open(OUTPUT_PATH, "w") as f:
        # loop through all the market ids - `i` here is just for the progress print below,
        # total_bets (separate variable) is what actually tracks the bet count
        for i, market_id in enumerate(market_ids, start=1):

            # get all bets for this market_id
            bets = get_all_bets(market_id)
            # write each bet as its own line - can be a lot per market, so write as we go, not all at once
            for b in bets:
                f.write(json.dumps(b) + "\n")
            # add this market's bet count to the running total
            total_bets += len(bets)
            # to stay under our per minute limit
            time.sleep(0.15)

            # logging for status
            if i % 25 == 0 or i == len(market_ids):
                print(f"  {i}/{len(market_ids)} markets, {total_bets} bets so far")

    # no dedup needed here either, but for 2 separate reasons, both required:
    #   1. market_ids is already deduped upstream - same trust/dependency as pull_market_answers.py
    #   2. the after-cursor pagination inside get_all_bets is stable on its own (see its docstring)
    # reason 1 matters even more here than in pull_market_answers.py though - if market_ids ever
    # had a dupe, this file wouldn't write one extra row, it would re-fetch and write a market's
    # ENTIRE bet history again, possibly thousands of rows. this is exactly what happened before
    # the fix: 63 duplicate markets cascaded into 5,391 duplicate bets
    print(f"Done. {total_bets} total bet records across {len(market_ids)} markets.")
    print(f"Saved to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
