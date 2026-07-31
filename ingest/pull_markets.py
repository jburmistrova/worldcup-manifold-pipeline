"""Search Manifold for World Cup 2026 markets, save full raw payloads as JSON Lines.

Writes the complete API response object per market — no field selection here.
Deciding which fields matter is downstream work (Spark/dbt), not extraction.
"""
import json
import time

import requests

BASE_URL = "https://api.manifold.markets/v0"
SEARCH_TERM = "World Cup 2026"
OUTPUT_PATH = "data/raw/worldcup_2026_markets.jsonl"


def search_markets(term, limit=100, offset=0):
    # response from a get for the api manifold
    # use params where we search "world cup", limit of 100, offset default is 0, but we increase it below
    resp = requests.get(
        f"{BASE_URL}/search-markets",
        params={"term": term, "limit": limit, "offset": offset, "filter": "all"},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def fetch_all(term):
    """Two real, separate bugs found here, not one:

    1. Small `limit` values (100, 200) silently truncate the result set —
       confirmed empirically: at limit=100 or 200, sports-linked markets
       (identifiable by a `sportsStartTimestamp` field) never appear at all,
       no matter how many pages you paginate through. At limit=1000, a
       single call cleanly returns everything (621 markets vs. the 389 this
       script used to find — a 60% undercount). Root cause isn't confirmed
       at the API-internals level, but the fix is: request the documented
       max (1000) per call, not a small page size.
    2. Separately, offset-based pagination isn't guaranteed stable across
       requests (e.g. ties in relevance ranking can reorder results between
       calls) — confirmed empirically: an earlier run produced 63 duplicate
       market rows. Dedupe by id as results come in rather than trust the
       API to never repeat a result. This is a known-unstable pattern in
       general (offset pagination + a sort that can tie), not a bug
       specific to Manifold — a careful client defends against it
       regardless of whose API it is.

    Kept the offset/pagination loop even though one call covers everything
    at our current scale — defense in depth if a term ever exceeds 1000
    results.
    """

    # offset and limit are the actual inputs to the api call
    # markets and seen_ids are NOT api inputs - they're our own running state that builds up across the loop
    markets = []
    seen_ids = set()
    offset = 0
    limit = 1000

    # while True + break is the standard pattern here - we can't know if a page is the
    # last one until AFTER we've already fetched it, so there's nothing to check up front
    # this stops in exactly 2 places below:
    #   1. api gives back nothing (not page) - catches the case where total markets is an
    #      exact multiple of `limit`
    #   2. page comes back smaller than `limit` (len(page) < limit) - the normal "we hit the end" case
    # we need both: if there were exactly 400 markets (4 full pages of 100), check #2 never
    # fires on that last full page, so we'd make one more call and check #1 catches the empty
    # page that comes back
    while True:
        # one page = up to `limit` markets starting at `offset`. offset=0 gets the first `limit`, offset=limit gets the next batch
        page = search_markets(term, limit=limit, offset=offset)

        # stop condition #1, see note above
        if not page:
            break

        # loop through the markets IN this one page (not "through pages" - the while loop does that)
        # dedupe inline, as each page comes in - not at the end on the full list, and not
        # downstream in dbt. this duplicate is caused by OUR pagination, not a business
        # judgment call about what counts as a duplicate, so it belongs here, at extraction time
        # offset pagination + a sort that can tie (relevance ranking) is a known-unstable
        # combo in general - not a bug specific to manifold's api. a careful client defends
        # against this regardless of whose api it is
        for m in page:
            if m["id"] not in seen_ids:
                seen_ids.add(m["id"])
                markets.append(m)

        # stop condition #2, see note above
        if len(page) < limit:
            break
        offset += limit

        # manifold has limits on what you can pull
        time.sleep(0.2)  # stay well under the 500 req/min limit
    return markets


def main():
    # run through pages in the api, and get the data
    markets = fetch_all(SEARCH_TERM)
    print(f"Fetched {len(markets)} markets for term {SEARCH_TERM!r}")

    # save to json
    with open(OUTPUT_PATH, "w") as f:
        for m in markets:
            f.write(json.dumps(m) + "\n")

    print(f"Saved to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
