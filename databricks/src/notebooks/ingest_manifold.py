# Databricks notebook source
# COMMAND ----------
# MAGIC %md
# MAGIC # Ingest: Manifold Markets
# MAGIC Databricks-notebook port of `ingest/pull_markets.py`, `pull_market_answers.py`,
# MAGIC and `pull_bets.py`. Same API calls, same pagination/dedup/retry logic
# MAGIC (ADR-0006, ADR-0007) -- the only real change is the output target: a
# MAGIC Unity Catalog Volume (`/Volumes/<catalog>/raw/landed_json/`) instead of
# MAGIC local `data/raw/`. Runs as three ordered steps in one notebook, same
# MAGIC dependency order `run_pipeline.sh` already encodes (answers and bets both
# MAGIC need markets' output first).

# COMMAND ----------
import os

dbutils.widgets.text("catalog", "worldcup_manifold", "Catalog")
dbutils.widgets.text("search_term", "World Cup 2026", "Search term")
dbutils.widgets.text("page_limit", "1000", "Page limit (bets)")
dbutils.widgets.text("max_retries", "5", "Max retries")

CATALOG = dbutils.widgets.get("catalog")
SEARCH_TERM = dbutils.widgets.get("search_term")
PAGE_LIMIT = int(dbutils.widgets.get("page_limit"))
os.environ["MAX_RETRIES"] = dbutils.widgets.get("max_retries")

VOLUME_DIR = f"/Volumes/{CATALOG}/raw/landed_json"
MARKETS_PATH = f"{VOLUME_DIR}/worldcup_2026_markets.jsonl"
ANSWERS_PATH = f"{VOLUME_DIR}/worldcup_2026_market_answers.jsonl"
BETS_PATH = f"{VOLUME_DIR}/worldcup_2026_bets.jsonl"

# COMMAND ----------
# MAGIC %run ./retry_get

# COMMAND ----------
import json
import time

BASE_URL = "https://api.manifold.markets/v0"

# COMMAND ----------
# MAGIC %md ## Step 1: markets (`pull_markets.py` port)
# MAGIC Same two real bugs this project already found and fixed apply here
# MAGIC unchanged: small `limit` values silently truncate `/search-markets`
# MAGIC (ADR-0007, fixed by requesting the documented max, 1000, per call), and
# MAGIC offset pagination isn't guaranteed stable, so dedupe by id as results
# MAGIC come in rather than trust the API not to repeat a result.

# COMMAND ----------
def search_markets(term, limit=100, offset=0):
    return get_with_retry(
        f"{BASE_URL}/search-markets",
        params={"term": term, "limit": limit, "offset": offset, "filter": "all"},
    )


def fetch_all_markets(term):
    markets, seen_ids = [], set()
    offset, limit = 0, 1000
    while True:
        page = search_markets(term, limit=limit, offset=offset)
        if not page:
            break
        for m in page:
            if m["id"] not in seen_ids:
                seen_ids.add(m["id"])
                markets.append(m)
        if len(page) < limit:
            break
        offset += limit
        time.sleep(0.2)
    return markets


markets = fetch_all_markets(SEARCH_TERM)
print(f"Fetched {len(markets)} markets for term {SEARCH_TERM!r}")

with open(MARKETS_PATH, "w") as f:
    for m in markets:
        f.write(json.dumps(m) + "\n")
print(f"Saved to {MARKETS_PATH}")

# COMMAND ----------
# MAGIC %md ## Step 2: market answers (`pull_market_answers.py` port)
# MAGIC `/search-markets` doesn't include the `answers` list for non-BINARY
# MAGIC markets at all; only `/market/{id}` has it, so this is one extra call
# MAGIC per non-BINARY market.

# COMMAND ----------
def get_market(market_id):
    return get_with_retry(f"{BASE_URL}/market/{market_id}")


non_binary_ids = [m["id"] for m in markets if m.get("outcomeType") != "BINARY"]
print(f"Fetching answer details for {len(non_binary_ids)} non-BINARY markets")

fetched, skipped = 0, 0
with open(ANSWERS_PATH, "w") as f:
    for market_id in non_binary_ids:
        market = get_market(market_id)
        answers = market.get("answers")
        if not answers:
            skipped += 1
            continue
        for a in answers:
            f.write(json.dumps(a) + "\n")
        fetched += 1
        time.sleep(0.15)

print(f"Done. {fetched} markets had answers written, {skipped} had none (e.g. POLL).")
print(f"Saved to {ANSWERS_PATH}")

# COMMAND ----------
# MAGIC %md ## Step 3: bets (`pull_bets.py` port)
# MAGIC `after` is a cursor anchored to a bet id, not a raw offset count, so it
# MAGIC doesn't have the same ranking-tie instability markets pagination did
# MAGIC (confirmed empirically in the original build: zero duplicate bet ids
# MAGIC across 1.17M+ bets).

# COMMAND ----------
def get_bets_page(contract_id, after=None):
    params = {"contractId": contract_id, "limit": PAGE_LIMIT, "order": "asc"}
    if after:
        params["after"] = after
    return get_with_retry(f"{BASE_URL}/bets", params=params)


def get_all_bets(contract_id):
    bets, after = [], None
    while True:
        page = get_bets_page(contract_id, after=after)
        if not page:
            break
        bets.extend(page)
        if len(page) < PAGE_LIMIT:
            break
        after = page[-1]["id"]
        time.sleep(0.15)
    return bets


market_ids = [m["id"] for m in markets]
print(f"Fetching bet history for {len(market_ids)} markets")

total_bets = 0
with open(BETS_PATH, "w") as f:
    for i, market_id in enumerate(market_ids, start=1):
        bets = get_all_bets(market_id)
        for b in bets:
            f.write(json.dumps(b) + "\n")
        total_bets += len(bets)
        time.sleep(0.15)
        if i % 25 == 0 or i == len(market_ids):
            print(f"  {i}/{len(market_ids)} markets, {total_bets} bets so far")

print(f"Done. {total_bets} total bet records across {len(market_ids)} markets.")
print(f"Saved to {BETS_PATH}")

# COMMAND ----------
dbutils.notebook.exit(json.dumps({
    "markets": len(markets),
    "answers_written_for": fetched,
    "bets": total_bets,
}))
