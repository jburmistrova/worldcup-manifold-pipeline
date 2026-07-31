"""For every non-BINARY market, pull /v0/market/{id} and save each raw
answer object as its own JSON line (full payload, no field selection —
same reasoning as pull_markets.py). BINARY markets are skipped since they
already carry a single top-level probability/resolution on the market
object itself — there's nothing extra to fetch for them.
"""
import json
import time

import requests

BASE_URL = "https://api.manifold.markets/v0"
MARKETS_PATH = "data/raw/worldcup_2026_markets.jsonl"
OUTPUT_PATH = "data/raw/worldcup_2026_market_answers.jsonl"

# this script exists because /v0/search-markets genuinely doesn't include the
# answers list at all for non-binary markets - verified directly, even now that
# we capture the full raw payload, 'answers' just isn't there. only /v0/market/{id}
# has it, so non-binary markets need this extra call, one per market
# (separately: multi-choice markets exist in the first place because some questions
# aren't yes/no - ex a match could be team1/team2/tie as 3 named answers - but that's
# WHY multi-choice exists, not why we need this extra api call. those are 2 different facts)
def get_market(market_id):
    # response from a get api call
    # no params like pull_markets.py - just a path param, and no pagination needed
    # since it's a direct lookup of one specific market by its id
    resp = requests.get(f"{BASE_URL}/market/{market_id}", timeout=10)
    resp.raise_for_status()
    return resp.json()


def load_non_binary_market_ids():
    # binary markets already have everything they need in markets.jsonl (single
    # probability/resolution), so we skip them - nothing to gain from the extra call
    # for non-binary markets we keep the id so we can make that extra /v0/market/{id} call above
    # we got this list from pull_markets.py
    market_ids = []
    with open(MARKETS_PATH) as f:
        for line in f:
            m = json.loads(line)
            if m.get("outcomeType") != "BINARY":
                market_ids.append(m["id"])
    return market_ids


def main():
    # get the market ids from pull_markets.py's output
    market_ids = load_non_binary_market_ids()
    print(f"Fetching answer details for {len(market_ids)} non-BINARY markets")

    # open path - write incrementally as each market's answers come in, not all at once at the end
    with open(OUTPUT_PATH, "w") as f:
        fetched, skipped = 0, 0
        # for each market id
        for market_id in market_ids:
            # fetch this market's full detail record using its id (not "finding" anything - we already have the id, we're using it)
            market = get_market(market_id)
            # pull the answers list out of that record
            answers = market.get("answers")
            # no answers list (e.g. POLL markets) - count it as skipped, nothing gets written for these
            if not answers:
                skipped += 1
                continue
            # write each answer as its own line to the output file
            for a in answers:
                f.write(json.dumps(a) + "\n")
            fetched += 1
            time.sleep(0.15)  # 500 req/min limit

    # no dedup logic in this file, for 2 separate reasons:
    #   1. market_ids is already deduped upstream in pull_markets.py - we're trusting that
    #      guarantee here, not re-checking it. if that upstream dedup ever broke, this file
    #      would silently start writing duplicate answers again with nothing here to catch it
    #   2. /v0/market/{id} is a direct lookup by one specific known id - no offset, no
    #      ranking, no pagination at all - so even ignoring reason #1, this endpoint can't
    #      have the same ranking-tie instability /v0/search-markets had
    print(f"Done. {fetched} markets had answers written, {skipped} had none (e.g. POLL).")
    print(f"Saved to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
