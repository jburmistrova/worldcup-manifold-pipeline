"""Pull trade history for a list of Polymarket conditionIds, save full raw
payloads as JSON Lines. Mirrors pull_bets.py's contract (retry-with-backoff,
raw-immutable JSONL), against a genuinely different trade shape: one
execution price per trade, not a before/after pair (see ADR-0004's
Postgres-target investigation for why that distinction matters downstream).

Takes the market list already pulled by pull_polymarket_markets.py and reads
each market's conditionId from it, rather than hardcoding IDs, so this stays
correct as the market list changes.
"""
import json
import os
import time

from retry_get import get_with_retry

BASE_URL = "https://data-api.polymarket.com"
MARKETS_PATH = "data/raw/polymarket_2026_events.jsonl"
OUTPUT_PATH = "data/raw/polymarket_2026_trades.jsonl"


def condition_ids_from_events(path):
    ids = []
    with open(path) as f:
        for line in f:
            event = json.loads(line)
            for market in event.get("markets", []):
                cid = market.get("conditionId")
                if cid:
                    ids.append(cid)
    return ids


def fetch_trades_for_market(condition_id, limit=500):
    # offset-paginated, same instability risk as every other offset-based
    # API this project has touched (see pull_markets.py's dedupe-by-id
    # pattern for Manifold); dedupe here for the same reason, not assumed
    # safe just because it's a different platform.
    trades = []
    seen = set()
    offset = 0

    while True:
        page = get_with_retry(
            f"{BASE_URL}/trades",
            params={"market": condition_id, "limit": limit, "offset": offset},
        )
        if not page:
            break

        for t in page:
            # no single natural primary key in this payload (no trade id
            # field); transactionHash + asset + timestamp is unique per
            # real fill in practice, close enough for in-run dedup here.
            key = (t.get("transactionHash"), t.get("asset"), t.get("timestamp"))
            if key not in seen:
                seen.add(key)
                trades.append(t)

        if len(page) < limit:
            break
        offset += limit
        time.sleep(0.1)

    return trades


def main():
    condition_ids = condition_ids_from_events(MARKETS_PATH)
    print(f"Fetching trades for {len(condition_ids)} markets")

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    total = 0
    with open(OUTPUT_PATH, "w") as out:
        for i, cid in enumerate(condition_ids, 1):
            trades = fetch_trades_for_market(cid)
            for t in trades:
                out.write(json.dumps(t) + "\n")
            total += len(trades)
            if i % 25 == 0:
                print(f"  {i}/{len(condition_ids)} markets, {total} trades so far")
            time.sleep(0.1)

    print(f"Done. {total} total trade records across {len(condition_ids)} markets.")
    print(f"Saved to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
