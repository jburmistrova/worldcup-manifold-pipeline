"""Search Polymarket for World Cup 2026 events, save full raw payloads as
JSON Lines. Mirrors pull_markets.py's contract (same shared retry helper,
same raw-immutable convention, see ADR-0006), against a genuinely different
API shape.

Writes the complete event object per event, including its nested markets
array, exactly as the API returns it. No field selection, no date filtering
here: this search also surfaces a real 2022 World Cup event ("World Cup
Matches", startDate 2022-11-21) despite the "2026" in the query, the same
class of contamination data_dictionary.md already documents for Manifold's
Cricket World Cup false positives. Deciding what's actually 2026-relevant is
downstream (staging) work, not extraction's job, matching this project's
existing convention: capture everything the search returns, filter later,
so a bad ingest-time filter can't quietly throw away a real market before
anyone gets a chance to notice.
"""
import json
import os
import time

from retry_get import get_with_retry

BASE_URL = "https://gamma-api.polymarket.com"
SEARCH_TERM = os.environ.get("POLYMARKET_SEARCH_TERM", "World Cup 2026")
OUTPUT_PATH = "data/raw/polymarket_2026_events.jsonl"


def search_events(term, page):
    # offset is a documented parameter but confirmed empirically to be
    # silently ignored (repeated calls with offset=50 return the same first
    # page as offset=0); page is the parameter that actually paginates,
    # confirmed the same way, by checking that page=2 returns different
    # event IDs than page=1. Not assumed from docs, since the docs page for
    # this specific endpoint 404s.
    return get_with_retry(
        f"{BASE_URL}/public-search",
        params={"q": term, "limit_per_type": 100, "page": page},
    )


def fetch_all(term):
    events = []
    seen_ids = set()
    page = 1

    while True:
        result = search_events(term, page)
        batch = result.get("events", [])

        if not batch:
            break

        for e in batch:
            if e["id"] not in seen_ids:
                seen_ids.add(e["id"])
                events.append(e)

        if not result.get("pagination", {}).get("hasMore"):
            break
        page += 1

        time.sleep(0.2)

    return events


def main():
    events = fetch_all(SEARCH_TERM)
    print(f"Fetched {len(events)} events for term {SEARCH_TERM!r}")

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")

    print(f"Saved to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
