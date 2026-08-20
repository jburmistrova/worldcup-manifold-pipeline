# Databricks notebook source
# COMMAND ----------
# MAGIC %md
# MAGIC # Ingest: Polymarket
# MAGIC Databricks-notebook port of `ingest/pull_polymarket_markets.py`,
# MAGIC `pull_polymarket_trades.py`, and `pull_polymarket_prices.py`. Same API
# MAGIC calls, chunking, and offset-ceiling handling (ADR-0011), writing to a
# MAGIC Unity Catalog Volume instead of local `data/raw/`.

# COMMAND ----------
import os

dbutils.widgets.text("catalog", "worldcup_manifold", "Catalog")
dbutils.widgets.text("search_term", "World Cup 2026", "Search term")
dbutils.widgets.text("max_retries", "5", "Max retries")

CATALOG = dbutils.widgets.get("catalog")
SEARCH_TERM = dbutils.widgets.get("search_term")
os.environ["MAX_RETRIES"] = dbutils.widgets.get("max_retries")

VOLUME_DIR = f"/Volumes/{CATALOG}/raw/landed_json"
EVENTS_PATH = f"{VOLUME_DIR}/polymarket_2026_events.jsonl"
TRADES_PATH = f"{VOLUME_DIR}/polymarket_2026_trades.jsonl"
PRICES_PATH = f"{VOLUME_DIR}/polymarket_2026_prices.jsonl"

# COMMAND ----------
# MAGIC %run ./retry_get

# COMMAND ----------
import json
import time
from datetime import datetime

import requests

# COMMAND ----------
# MAGIC %md ## Step 1: events/markets (`pull_polymarket_markets.py` port)
# MAGIC `page` (not the documented `offset`, confirmed empirically ignored) is
# MAGIC what actually paginates `/public-search`.

# COMMAND ----------
GAMMA_URL = "https://gamma-api.polymarket.com"


def search_events(term, page):
    return get_with_retry(
        f"{GAMMA_URL}/public-search",
        params={"q": term, "limit_per_type": 100, "page": page},
    )


def fetch_all_events(term):
    events, seen_ids = [], set()
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


events = fetch_all_events(SEARCH_TERM)
print(f"Fetched {len(events)} events for term {SEARCH_TERM!r}")

with open(EVENTS_PATH, "w") as f:
    for e in events:
        f.write(json.dumps(e) + "\n")
print(f"Saved to {EVENTS_PATH}")

# COMMAND ----------
# MAGIC %md ## Step 2: trades (`pull_polymarket_trades.py` port)
# MAGIC `/trades` errors past offset 10,000 ("max historical trades offset
# MAGIC exceeded", ADR-0011) -- a real, confirmed ceiling, treated as "done",
# MAGIC not retried.

# COMMAND ----------
DATA_API_URL = "https://data-api.polymarket.com"
MAX_OFFSET = 10000


def condition_ids_from_events(events):
    ids = []
    for event in events:
        for market in event.get("markets", []):
            cid = market.get("conditionId")
            if cid:
                ids.append(cid)
    return ids


def fetch_trades_for_market(condition_id, limit=500):
    trades, seen = [], set()
    offset = 0
    while offset < MAX_OFFSET:
        try:
            page = get_with_retry(
                f"{DATA_API_URL}/trades",
                params={"market": condition_id, "limit": limit, "offset": offset},
            )
        except requests.exceptions.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 400:
                break
            raise
        if not page:
            break
        for t in page:
            key = (t.get("transactionHash"), t.get("asset"), t.get("timestamp"))
            if key not in seen:
                seen.add(key)
                trades.append(t)
        if len(page) < limit:
            break
        offset += limit
        time.sleep(0.1)
    return trades


condition_ids = condition_ids_from_events(events)
print(f"Fetching trades for {len(condition_ids)} markets")

total_trades = 0
with open(TRADES_PATH, "w") as out:
    for i, cid in enumerate(condition_ids, 1):
        trades = fetch_trades_for_market(cid)
        for t in trades:
            out.write(json.dumps(t) + "\n")
        total_trades += len(trades)
        if i % 25 == 0:
            print(f"  {i}/{len(condition_ids)} markets, {total_trades} trades so far")
        time.sleep(0.1)

print(f"Done. {total_trades} total trade records across {len(condition_ids)} markets.")
print(f"Saved to {TRADES_PATH}")

# COMMAND ----------
# MAGIC %md ## Step 3: price history (`pull_polymarket_prices.py` port)
# MAGIC `/prices-history` isn't count-capped like `/trades`, but does cap the
# MAGIC time span per request (~20-30 days, ADR-0011), so full coverage means
# MAGIC walking each market's lifetime in 14-day chunks.

# COMMAND ----------
CLOB_URL = "https://clob.polymarket.com"
CHUNK_SECONDS = 14 * 24 * 60 * 60
FIDELITY_MINUTES = 60


def _parse_ts(iso_string):
    if not iso_string:
        return None
    return int(datetime.fromisoformat(iso_string.replace("Z", "+00:00")).timestamp())


def markets_from_events(events):
    markets = []
    for event in events:
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
            f"{CLOB_URL}/prices-history",
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


price_markets = markets_from_events(events)
print(f"Fetching price history for {len(price_markets)} markets")

total_prices = 0
with open(PRICES_PATH, "w") as out:
    for i, m in enumerate(price_markets, 1):
        points = fetch_price_history(m["token_id"], m["start_ts"], m["end_ts"])
        for p in points:
            out.write(json.dumps({
                "market_id": m["market_id"],
                "condition_id": m["condition_id"],
                "token_id": m["token_id"],
                "t": p["t"],
                "p": p["p"],
            }) + "\n")
        total_prices += len(points)
        if i % 25 == 0:
            print(f"  {i}/{len(price_markets)} markets, {total_prices} price points so far")

print(f"Done. {total_prices} total price points across {len(price_markets)} markets.")
print(f"Saved to {PRICES_PATH}")

# COMMAND ----------
dbutils.notebook.exit(json.dumps({
    "events": len(events),
    "trades": total_trades,
    "price_points": total_prices,
}))
