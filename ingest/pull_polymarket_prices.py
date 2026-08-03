"""Pull full-history price series for Polymarket markets via /prices-history,
save full raw payloads as JSON Lines.

Not /trades: confirmed empirically that /trades caps at the 10,000 most
recent records per market with no way to page further back, and for a
hyper-liquid market that window can cover only a few hours, not the
pre-kickoff-era history this project's calibration work actually needs.
/prices-history isn't count-capped, but it does cap how wide a single
request's time span can be ("interval is too long" past roughly 20-30 days,
confirmed empirically, exact boundary not pinned down since a safe smaller
chunk size works regardless), so full coverage means walking a market's
lifetime in chunks and stitching them together, not one "interval=max" call.

Only the first (index 0, confirmed empirically to always be "Yes") clobTokenId
per market is pulled: a price series for one binary outcome, since the other
side is its complement and pulling both would double the requests for no new
information, canonical probability here means P(Yes), matching Manifold's
own prob = P(YES) convention.
"""
import json
import os
import time
from datetime import datetime, timezone

from retry_get import get_with_retry

BASE_URL = "https://clob.polymarket.com"
MARKETS_PATH = "data/raw/polymarket_2026_events.jsonl"
OUTPUT_PATH = "data/raw/polymarket_2026_prices.jsonl"
CHUNK_SECONDS = 14 * 24 * 60 * 60  # 14 days: confirmed working, comfortably under the ~20-30 day span cap
FIDELITY_MINUTES = 60


def _parse_ts(iso_string):
    if not iso_string:
        return None
    return int(datetime.fromisoformat(iso_string.replace("Z", "+00:00")).timestamp())


def markets_from_events(path):
    markets = []
    with open(path) as f:
        for line in f:
            event = json.loads(line)
            for m in event.get("markets", []):
                token_ids_raw = m.get("clobTokenIds")
                if not token_ids_raw:
                    continue
                token_ids = json.loads(token_ids_raw)
                if not token_ids:
                    continue
                start_ts = _parse_ts(m.get("createdAt")) or _parse_ts(m.get("startDate"))
                end_ts = _parse_ts(m.get("closedTime")) or _parse_ts(m.get("endDate"))
                if not start_ts or not end_ts or end_ts <= start_ts:
                    continue
                markets.append({
                    "market_id": m["id"],
                    "condition_id": m.get("conditionId"),
                    "token_id": token_ids[0],
                    "start_ts": start_ts,
                    "end_ts": min(end_ts, int(time.time())),
                })
    return markets


def fetch_price_history(token_id, start_ts, end_ts):
    points = []
    chunk_start = start_ts
    while chunk_start < end_ts:
        chunk_end = min(chunk_start + CHUNK_SECONDS, end_ts)
        result = get_with_retry(
            f"{BASE_URL}/prices-history",
            params={
                "market": token_id,
                "startTs": chunk_start,
                "endTs": chunk_end,
                "fidelity": FIDELITY_MINUTES,
            },
        )
        points.extend(result.get("history", []))
        chunk_start = chunk_end
        time.sleep(0.1)
    return points


def main():
    markets = markets_from_events(MARKETS_PATH)
    print(f"Fetching price history for {len(markets)} markets")

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    total = 0
    with open(OUTPUT_PATH, "w") as out:
        for i, m in enumerate(markets, 1):
            points = fetch_price_history(m["token_id"], m["start_ts"], m["end_ts"])
            for p in points:
                out.write(json.dumps({
                    "market_id": m["market_id"],
                    "condition_id": m["condition_id"],
                    "token_id": m["token_id"],
                    "t": p["t"],
                    "p": p["p"],
                }) + "\n")
            total += len(points)
            if i % 25 == 0:
                print(f"  {i}/{len(markets)} markets, {total} price points so far")

    print(f"Done. {total} total price points across {len(markets)} markets.")
    print(f"Saved to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
