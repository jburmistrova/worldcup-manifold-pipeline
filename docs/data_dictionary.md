# Data Dictionary

## Format note

Raw ingestion writes **JSON Lines** (`data/raw/*.jsonl`), one complete, unmodified API response object per line, not a hand-picked subset of fields. This project started with CSV and a curated field list; both choices turned out to be mistakes, documented in [ADR-0006](decisions/0006-raw-layer-jsonl-immutable.md). The tables below describe the fields Spark actually selects out of the full raw payload for `data/processed/*.parquet`. The raw JSONL files contain more fields than are listed here (e.g. `pool`, `mechanism`, `uniqueBettorCount` on markets), preserved as-is in case they're useful later, just not currently carried downstream. Each section also has a `-> dbt` table mapping that Parquet column to its renamed, typed dbt staging column. Naming convention in brief: `_id` for identifiers, `_at` for real timestamps (converted from raw epoch-ms, not left as integers under a misleading name), `is_`/`has_` for booleans, and family-word-first grouping for fields that share a concept (`prob_before`/`prob_after`/`prob_limit`, `amount`/`amount_order`) so related columns sort and browse together.

## `data/raw/worldcup_2026_markets.jsonl` -> `data/processed/markets`

Produced by [`ingest/pull_markets.py`](../ingest/pull_markets.py), one JSON object per line, one per Manifold market matching the search term `"World Cup 2026"`. **621 rows.** A prior version of this script found only 389. 232 real markets were silently missing due to a pagination bug, found and fixed in [ADR-0007](decisions/0007-search-limit-truncation.md).

| Field | Type | Notes |
|---|---|---|
| `id` | string | Manifold's internal market ID. |
| `question` | string | The market's title, e.g. "Will Norway defeat Senegal in the first round of World Cup 2026?" |
| `slug` | string | URL-safe identifier. |
| `url` | string | Returned directly by the API. The earlier CSV version reconstructed this manually from `creatorUsername` + `slug` because it seemed absent; capturing the full raw payload showed it was there all along. |
| `outcomeType` | string | `BINARY` (single yes/no probability), `MULTIPLE_CHOICE` (a set of sub-answers, each with its own probability, see caveat below), `MULTI_NUMERIC` (numeric-range answers), or `POLL` (no real-money resolution). Counts in this dataset: 335 `MULTIPLE_CHOICE`, 271 `BINARY`, 9 `MULTI_NUMERIC`, 6 `POLL`. |
| `isResolved` | bool | Whether the market has settled. Native JSON boolean, no string-parsing caveat needed (contrast with the CSV era, see History below). |
| `resolution` | string | **Meaning depends on `outcomeType`.** Confirmed empirically, not assumed: for `BINARY`, one of `YES`, `NO`, `MKT` (resolved to a probability rather than a clean yes/no), or `CANCEL` (voided). For `MULTIPLE_CHOICE`, it's the **winning answer's ID**, not human-readable on its own. Prefer the per-answer `resolution` in the answers table below; it's already YES/NO. Empty until resolved. |
| `probability` | float, 0-1 | Current (or final, if resolved) implied probability. **Empty for `MULTIPLE_CHOICE` markets**, those carry probability per-answer. |
| `volume` | float | Cumulative trading volume in Mana (Manifold's play-money currency), not USD. |
| `totalLiquidity` | float | Size of the automated-market-maker's subsidy pool, in Mana, **not** the same as `volume` (turnover vs. AMM depth). Low-liquidity markets are noisier; a natural confidence weight for later calibration analysis. |
| `createdTime` | int | Unix epoch milliseconds, UTC. |
| `closeTime` | int | Same format, when betting closes on the market. Not a reliable proxy for match kickoff time. Verified against a market whose question stated an exact date, `closeTime` was set to a round "end of day" value, and `resolutionTime` for the same market lagged 4 days behind it. |
| `resolutionTime` | int | Same format, empty until resolved. |
| `sportsStartTimestamp` | string (ISO 8601) | Present on 108 of 621 markets (sports-integrated markets specifically), a real, precise match kickoff time, e.g. `"2026-06-30T01:00:00Z"`. Found while investigating whether a true pre-kickoff calibration analysis was possible; see [ADR-0007](decisions/0007-search-limit-truncation.md). Carried into Parquet as `sports_start_at` once it started driving real matching logic; see [ADR-0008](decisions/0008-kickoff-time-enrichment-openfootball.md). |

**Non-determinism, named plainly:** re-running this script won't necessarily return the identical set of markets, since `/v0/search-markets` ranks by relevance and new markets can appear. Confirmed small (single-digit) variation across same-`limit` runs. The 232-market discrepancy found and documented in ADR-0007 was a real bug (`limit` too small), not this kind of ordinary variation.

**Search contamination, found while building [ADR-0008](decisions/0008-kickoff-time-enrichment-openfootball.md)'s kickoff-time matching, not by inspection beforehand:** the search term `"World Cup 2026"` isn't scoped to football at all. At least 3 ingested markets are actually about the **Cricket T20 World Cup** (e.g. `"Cricket T20 2026 World Cup - Semifinal 2 - Who will win ENG vs IND?"`), and they share team codes like `ENG` with real football teams. Confirmed harmless for the kickoff-time matcher specifically: a cricket-only code like `IND` doesn't resolve against any of the 48 real World Cup 2026 football teams, so matching fails safe instead of producing a wrong cross-sport result. But it's a real reminder that a keyword search filters on text, not on topic, and this dataset isn't purely football, something worth knowing before trusting any market count as "the football markets."

### -> `stg_manifold_markets` (dbt)

Pure rename + type conversion, no rows dropped, no filtering. Every market from the source is included.

| Raw (Parquet) | dbt staging column | Notes |
|---|---|---|
| `id` | `market_id` | |
| `question` | `question` | |
| `slug` | `slug` | |
| `url` | `url` | |
| `outcomeType` | `outcome_type` | |
| `resolution` | `resolution` | |
| `isResolved` | `is_resolved` | |
| `probability` | `prob` | abbreviated to match `prob_before`/`prob_after`/`prob_limit` in `stg_manifold_bets`, same concept, same name, across every table |
| `volume` | `volume` | |
| `totalLiquidity` | `liquidity_total` | family-word-first: `liquidity` is the concept, `total` the modifier |
| `createdTime` | `created_at` | epoch-ms int -> real `TIMESTAMP`, via DuckDB's `epoch_ms()` |
| `closeTime` | `closed_at` | same conversion |
| `resolutionTime` | `resolved_at` | same conversion |

## `data/raw/worldcup_2026_market_answers.jsonl` -> `data/processed/market_answers`

Produced by [`ingest/pull_market_answers.py`](../ingest/pull_market_answers.py). For every market above whose `outcomeType` isn't `BINARY`, calls `GET /v0/market/{id}` and writes one line per answer in its `answers` array. `BINARY` markets are skipped. They already carry a single top-level probability/resolution. Each answer behaves like its own mini binary market. **4,545 rows**, from 350 non-BINARY markets (335 `MULTIPLE_CHOICE` + 9 `MULTI_NUMERIC` + 6 `POLL` = 350; 344 of them had at least one answer, 6 `POLL` markets had none).

| Field | Type | Notes |
|---|---|---|
| `contractId` | string | Foreign key to `id` in the markets table. A market has many answers. |
| `id` | string | This answer's own ID, the value that shows up as the parent market's top-level `resolution` for `MULTIPLE_CHOICE` markets. |
| `index` | int | Display order of the answer within the market (0-based). |
| `text` | string | Human-readable answer label, e.g. "Lionel Messi to score at least one goal." |
| `isOther` | bool | Whether this is Manifold's auto-generated catch-all "Other" answer. |
| `probability` | float, 0-1 | Current (or final) probability for this specific answer. |
| `resolution` | string | Already human-readable, no ID to decode. But **correcting an earlier claim here that turned out to be incomplete**: this isn't only `YES`/`NO`. Confirmed empirically across the full dataset: `NO` (1,697), `YES` (925), empty/unresolved (1,812), `CANCEL` (70), `MKT` (41). Same set of values as the parent market's `resolution` field for `BINARY` markets, just per-answer. Anything building calibration analysis on this needs `WHERE resolution IN ('YES', 'NO')` explicitly. `CANCEL`/`MKT` rows have no clean ground truth. |
| `resolutionProbability` | float, 0-1 | The probability at the moment this answer resolved, the key input for the market-calibration mart later. |
| `resolutionTime` | int | Epoch ms UTC. |
| `volume` | float | Trading volume in Mana, scoped to this answer. |
| `totalLiquidity` | float | AMM liquidity pool depth, scoped to this answer. |
| `createdTime` | int | Epoch ms UTC. |

### -> `stg_manifold_market_answers` (dbt)

Pure rename + type conversion, no rows dropped.

| Raw (Parquet) | dbt staging column | Notes |
|---|---|---|
| `contractId` | `market_id` | renamed to match. Every staging table uses the same join-key name, which is what let the earlier cross-table join work with zero friction |
| `id` | `answer_id` | `id` alone would collide/confuse once joined against `market_id` |
| `index` | `answer_index` | same reason, explicit about which entity it belongs to |
| `text` | `answer_text` | |
| `isOther` | `is_other` | |
| `probability` | `prob` | |
| `resolution` | `resolution` | |
| `resolutionProbability` | `prob_resolution` | groups alphabetically with `prob` |
| `volume` | `volume` | |
| `totalLiquidity` | `liquidity_total` | |
| `createdTime` | `created_at` | epoch-ms -> `TIMESTAMP` |
| `resolutionTime` | `resolved_at` | epoch-ms -> `TIMESTAMP` |

## `data/raw/worldcup_2026_bets.jsonl` -> `data/processed/bets`

Produced by [`ingest/pull_bets.py`](../ingest/pull_bets.py). Every bet object `GET /v0/bets` returns for every market above, paginated via the `after` bet-ID cursor. Deliberately unfiltered. Filtering is dbt's job (`stg_manifold_bets`), not this script's, per [ADR-0005](decisions/0005-elt-not-etl-transformation-lives-in-dbt.md). **1,176,547 rows, zero duplicate bet IDs**, confirmed directly. The `after` cursor pagination used here doesn't share the offset-based instability that caused the markets truncation/duplication bugs ([ADR-0006](decisions/0006-raw-layer-jsonl-immutable.md), [ADR-0007](decisions/0007-search-limit-truncation.md)).

| Field | Type | Notes |
|---|---|---|
| `id` | string | Bet ID. |
| `contractId` | string | Foreign key to `id` in the markets table. |
| `userId` | string | The bettor. Not resolved to a username, not needed for this analysis. |
| `outcome` | string | `YES` or `NO`, which side this bet was on. |
| `amount` | float | Mana staked. **Can be negative for two different reasons, confirmed separately, not assumed:** redemptions (see below) are always negative, but so are genuine **sell trades**, unwinding an existing position back into the pool. Sells are real, price-moving activity (`probBefore != probAfter`, unlike redemptions) and correctly remain in `stg_manifold_bets` after filtering. A buy's `amount` is usually round (a human typed a stake into the bet box); a sell's is essentially never round, same reason `shares` isn't. Both are computed by the AMM's pricing curve at that moment, not chosen by a person. |
| `shares` | float | Shares bought/sold. Almost never a round number. Derived from the AMM's pricing curve given the market's state at that instant, not user input (contrast with `amount` on a buy, which usually *is* round, since that's what the user actually typed). |
| `probBefore` / `probAfter` | float, 0-1 | The market's implied probability immediately before and after this specific bet. **Core field for probability-over-time reconstruction.** Ordering by `createdTime` and taking `probAfter` per bet gives the full price path. |
| `createdTime` | int | Epoch ms UTC. |
| `isFilled` | bool | Whether the bet actually executed. `false` for limit orders still resting unfilled. **Absent entirely** (not `false`, the key doesn't exist) on redemption records. |
| `isCancelled` | bool | Whether a limit order was cancelled before filling. |
| `isRedemption` | bool | Share redemptions (opposing YES/NO positions held by the same user cancelling out for a payout), **not a real trade**. `probBefore == probAfter` on every redemption checked; they don't move the market. |
| `limitProb` | float, 0-1 | The limit price requested, only present on limit orders. |
| `orderAmount` | float | The amount requested for a limit order, which may differ from `amount` (the amount actually filled). |

**Critical filtering caveat, confirmed on the final data:** of 1,176,547 total rows, only **212,749 (18.1%)** are real trades. **758,308 (64.5%)** are cancelled/unfilled limit orders that never executed. **203,258 (17.3%)** are redemptions with zero price impact, confirmed directly (`probBefore == probAfter` on every redemption checked). **1,367 (0.1%)** are zero-amount "seeding" events: multiple rows sharing the exact same timestamp, `probBefore == probAfter`, appearing at market/answer creation, read as a system-generated initial share allocation rather than a real trade. Caught because it broke a downstream calculation (`0 / 0` in a running VWAP produced `NaN`, which a bounds test then flagged), not by inspection. A good example of a test earning its keep. Worth noting the proportions shifted noticeably after [ADR-0007](decisions/0007-search-limit-truncation.md)'s fix recovered 232 previously-missing markets (real-trade share dropped from ~33% to ~18%, cancelled share rose from ~34% to ~65%). The newly-recovered markets, several of them high-volume sports-linked or mega prop-bet markets, apparently carry a lot more limit-order/cancelled-order activity than the smaller markets in the original, incomplete dataset. A naive `AVG(probAfter)` or VWAP over the raw file would be badly wrong. Over 80% of it is noise for reconstructing what the market actually believed at each point in time. The correct filter for "real trade" is `isFilled = true AND isCancelled = false AND amount != 0`. This logic belongs in `stg_manifold_bets`, tested there, not silently baked into ingestion.

### -> `stg_manifold_bets` (dbt)

**Not a pure rename.** This is the one staging model that also filters rows. `WHERE isFilled = true AND isCancelled = false AND amount != 0` drops the ~81.9% of rows that are cancelled/unfilled orders, redemptions, or zero-amount seeding events, per the caveat above. 1,176,547 raw rows -> 212,749 staged rows.

| Raw (Parquet) | dbt staging column | Notes |
|---|---|---|
| `id` | `bet_id` | |
| `contractId` | `market_id` | |
| `answerId` | `answer_id` | present (a real id) on `MULTIPLE_CHOICE`-market bets, absent (not just null) on `BINARY`-market bets. Each answer has its own independent probability track. Missing from the original field list; added after checking the raw payload directly while designing `int_market_implied_probability`, not assumed present. |
| `userId` | `user_id` | |
| `outcome` | `outcome` | |
| `amount` | `amount` | |
| `orderAmount` | `amount_order` | family-word-first, groups with `amount` |
| `shares` | `count_share` | `count` as the family word, anticipates other count-type fields later (e.g. the raw `uniqueBettorCount` field on markets, not yet carried through, would become `count_bettor` under the same convention) |
| `probBefore` | `prob_before` | |
| `probAfter` | `prob_after` | |
| `limitProb` | `prob_limit` | |
| `createdTime` | `created_at` | epoch-ms -> `TIMESTAMP` |
| `isFilled` | `is_filled` | also drives the `WHERE` filter above |
| `isCancelled` | `is_cancelled` | also drives the `WHERE` filter above |
| `isRedemption` | `is_redemption` | |

## Polymarket

Optional second data source, gated behind `INCLUDE_POLYMARKET` (default: off, see [ADR-0012](decisions/0012-cross-platform-canonical-trade-schema.md)). Three raw datasets, no equivalent of Manifold's separate "market answers" pull: Polymarket's per-team markets already carry everything needed, nothing has to be fetched in a second pass the way Manifold's non-`BINARY` answers do.

### `data/raw/polymarket_2026_events.jsonl` -> `data/processed/polymarket_markets`

Produced by [`ingest/pull_polymarket_markets.py`](../ingest/pull_polymarket_markets.py), one JSON object per line, one per Polymarket **event** matching `/public-search?q=World Cup 2026`, paginated by `page` (a real offset, unlike Manifold's `limit`-truncation bug in ADR-0007, confirmed to return the API's own reported `totalResults` exactly). **488 events.** Each event nests a `markets` array, Polymarket's equivalent of one binary sub-question (e.g. one team's outright-winner market); an outright-winner event like "World Cup Winner" contains 50+ of these, linked by a shared `negRiskMarketID`, not one multi-choice market the way Manifold's is (see [ADR-0011](decisions/0011-polymarket-api-shape-and-full-history-pricing.md)). Spark explodes this array; **6,359 nested markets** across the 488 events.

| Field | Level | Type | Notes |
|---|---|---|---|
| `id` | event | string | Aliased `event_id` in Parquet. |
| `title` | event | string | Aliased `event_title`. |
| `id` | market | string | The individual binary market's own id, distinct from the event id above. |
| `conditionId` | market | string | The market's on-chain condition id, unique per binary market, used to join against trades and prices. |
| `question` | market | string | Full question text, e.g. "Will Spain win the World Cup?" |
| `groupItemTitle` | market | string | Short label for this market within its event, e.g. the team name alone, "Spain." Polymarket's equivalent of Manifold's per-answer `text`. |
| `negRiskMarketID` | market | string | Present only when this market belongs to a grouped ("negRisk") event; absent (not just null) on genuine standalone binary questions. Drives the canonical `market_id`/`answer_id` split below, the same way Manifold's `outcomeType` drives its own. |
| `outcomes` | market | string (JSON array) | e.g. `'["Yes", "No"]'`. Carried through unparsed; not currently used downstream. |
| `outcomePrices` | market | string (JSON array) | e.g. `'["0.02", "0.98"]'` while trading, `'["1", "0"]'` or `'["0", "1"]'` once resolved. Polymarket's equivalent of Manifold's `resolution` + `probability` combined into one field; parsed in staging, not here (ADR-0005: no business logic in ingestion/flatten). |
| `clobTokenIds` | market | string (JSON array) | The two CLOB token ids backing this market's Yes/No order books, `[0]` is Yes, confirmed empirically, never assumed (see `pull_polymarket_prices.py`'s own docstring). |
| `volume` | market | float | Cumulative trading volume, in USD, real money, unlike Manifold's Mana-denominated `volume`. |
| `liquidity` | market | float | Order-book depth, Polymarket's rough equivalent of Manifold's `totalLiquidity`, not the same mechanism (CLOB order book vs. AMM subsidy pool). |
| `active` | market | bool | Whether the market is still open for trading. |
| `closed` | market | bool | Whether the market has stopped trading (Polymarket's equivalent of Manifold's `isResolved`, confirmed in practice to track resolution for this dataset's markets, not merely "trading halted"). |
| `createdAt` | market | string (ISO 8601) | |
| `startDate` | market | string (ISO 8601) | |
| `endDate` | market | string (ISO 8601) | |
| `closedTime` | market | string (ISO 8601) | When the market actually closed/resolved, empty otherwise. |

#### -> `stg_polymarket_markets` (dbt)

Not a pure rename, same "the model that decodes identity" role `stg_manifold_markets`/`stg_manifold_market_answers` split between them, done in one model here since Polymarket's grouping is flatter.

| Raw (Parquet) | dbt staging column | Notes |
|---|---|---|
| `coalesce(neg_risk_market_id, market_id)` | `market_id` | canonical, group-level id: the shared `negRiskMarketID` when grouped, else the market's own id |
| `neg_risk_market_id is not null` ? `market_id` : `NULL` | `answer_id` | mirrors Manifold's `answerId`: present only when grouped, `NULL` on a genuine standalone binary market, exactly like a Manifold `BINARY` bet |
| `market_id` (raw) | `polymarket_market_id` | this individual market's own raw id, kept for traceability once the canonical `market_id` above points at the group instead |
| `conditionId` | `condition_id` | the real join key to trades and prices, unaffected by the negRisk grouping logic above |
| `question` | `question` | |
| `groupItemTitle` | `answer_text` | |
| n/a | `outcome_type` | hardcoded `'BINARY'`: every Polymarket market ingested here is binary at the individual-market level, unlike Manifold |
| `outcome_prices` (parsed) | `resolution` | `'YES'`/`'NO'`/`NULL`, decoded from `outcomePrices[0] == '1'` or `[1] == '1'` once `closed` |
| `closed` | `is_resolved` | |
| `outcome_prices` (parsed) | `prob` | `outcomePrices[0]`, cast to `double` |
| `volume` | `volume` | |
| `liquidity` | `liquidity_total` | |
| `created_at` / `closed_time` | `created_at` / `closed_at` / `resolved_at` | string -> `TIMESTAMP`; `resolved_at` reuses `closed_time`, Polymarket has no separate resolution timestamp the way Manifold does |
| `clob_token_ids` (parsed) | `yes_token_id` | `clobTokenIds[0]`, the join key into `stg_polymarket_prices`/`stg_polymarket_trades`' `token_id`/`asset` |

### `data/raw/polymarket_2026_trades.jsonl` -> `data/processed/polymarket_trades`

Produced by [`ingest/pull_polymarket_trades.py`](../ingest/pull_polymarket_trades.py), `GET /trades` per market `conditionId`, paginated by offset. **Hard-capped at the 10,000 most-recent records per market**, no way to page further back (confirmed via the API's own `"max historical trades offset of 10000 exceeded"` error, see [ADR-0011](decisions/0011-polymarket-api-shape-and-full-history-pricing.md)); real, load-bearing truncation, not a bug, which is why `stg_polymarket_prices` below is the primary reconstruction source, not this table. **4,378,920 rows across 6,358 markets.**

| Field | Type | Notes |
|---|---|---|
| `conditionId` | string | Foreign key to `condition_id` in the markets table. |
| `asset` | string | The CLOB token id this specific fill traded, matches either side's `clobTokenIds` entry. |
| `side` | string | `BUY` or `SELL`. |
| `outcome` | string | Human-readable, `"Yes"` or `"No"`. |
| `outcomeIndex` | int | `0` for Yes, `1` for No, confirmed empirically to always align this way across the dataset. |
| `size` | float | Shares traded. Polymarket's equivalent of Manifold's `shares`. |
| `price` | float, 0-1 | Execution price for this fill, Polymarket's equivalent of a single point on Manifold's `probBefore`/`probAfter` pair; a fill has one price, not a before/after. |
| `timestamp` | int | Epoch **seconds** (not milliseconds, unlike Manifold's `createdTime`), UTC. |
| `transactionHash` | string | On-chain transaction hash. Multiple fills can share one hash if a single transaction settled several trades atomically, which is why it alone isn't a usable trade id. |

#### -> `stg_polymarket_trades` (dbt)

Filters to Yes-side fills only (`WHERE outcomeIndex = 0`); No-side trades are the complementary view of the same information, matching the Yes-only convention `stg_polymarket_prices` already uses and Manifold's own `prob = P(YES)` convention.

| Raw (Parquet) | dbt staging column | Notes |
|---|---|---|
| n/a | `trade_id` | synthesized: `md5()` over `transactionHash`, `conditionId`, `asset`, `side`, `size`, `price`, `timestamp` together, since no single raw field is a usable id on its own (a `transactionHash` alone can cover several fills) |
| `conditionId` | `condition_id` | |
| `asset` | `token_id` | |
| `side` | `side` | |
| `size` | `size` | |
| `price` | `price` | |
| `timestamp` | `created_at` | epoch-seconds -> plain `TIMESTAMP` (not `TIMESTAMP WITH TIME ZONE`; a real mismatch against Manifold's own UTC-naive columns caught once this fed the shared union, see `int_all_market_ticks.sql`) |

### `data/raw/polymarket_2026_prices.jsonl` -> `data/processed/polymarket_prices`

Produced by [`ingest/pull_polymarket_prices.py`](../ingest/pull_polymarket_prices.py), `GET /prices-history` per market's Yes token (`clobTokenIds[0]` only), walked across each market's lifetime in 14-day chunks and stitched together (the endpoint isn't count-capped like `/trades`, but is span-capped per request at roughly 20-30 days, confirmed empirically, see ADR-0011), `fidelity=60` (hourly samples). **The primary source for Polymarket probability reconstruction**, not `/trades`, specifically because it isn't recency-capped. **3,209,795 rows across 6,357 markets.**

| Field | Type | Notes |
|---|---|---|
| `market_id` | string | Carried through from the market list used to drive the pull, not part of the CLOB API's own response. |
| `condition_id` | string | Same, the real join key downstream. |
| `token_id` | string | The Yes-side CLOB token this series belongs to. |
| `t` | int | Epoch seconds, UTC. |
| `p` | float, 0-1 | Sampled price at that timestamp. No trade size accompanies it: a price sample, not an executed fill. |

#### -> `stg_polymarket_prices` (dbt)

Pure rename + type conversion, no rows dropped.

| Raw (Parquet) | dbt staging column | Notes |
|---|---|---|
| `market_id` | `market_id` | |
| `condition_id` | `condition_id` | |
| `token_id` | `token_id` | |
| `t` | `created_at` | epoch-seconds -> plain `TIMESTAMP`, same reasoning as `stg_polymarket_trades.created_at` above |
| `p` | `price` | |

## History: the CSV era (superseded by ADR-0006, not deleted)

The project started with CSV as the raw format, with real, instructive consequences. Kept here rather than erased, since they're genuinely useful "what broke" material:

- **A text field with a nested quoted phrase** (`"Shocking decision, Ref!": ...`) caused Spark's CSV parser to mis-split the row at an internal comma, shifting every column after it by one. Python's own `csv` module parsed it correctly; Spark's didn't, by default.
- **Three markets had a literal newline embedded in `question`.** Spark's default (non-`multiLine`) CSV reader treated each as two physical rows, inflating the market count by exactly 3.
- **A pagination-instability bug produced 63 duplicate markets**, which cascaded into 128 duplicate answers and 5,391 duplicate bets. A real bug, unrelated to the file format, but the fix was first applied incorrectly (overwriting raw CSVs in place, destroying the original snapshot) before being corrected properly.

All three are exactly why the raw format changed to JSON Lines and why raw data is now treated as immutable. Full reasoning in [ADR-0006](decisions/0006-raw-layer-jsonl-immutable.md). The original CSVs (as they stood after the in-place dedup, not the true original) are archived at `data/archive/csv_v1/`, not deleted.

## Open questions / not yet handled

- None blocking on the Manifold side. All three raw files are ingested via the JSON pipeline, deduplicated correctly, and flattened to Parquet with real native types.
- Polymarket now has its own committed CI fixture ([`tests/fixtures/raw/`](../tests/fixtures/raw/), 2 real events), see `docs/data_engineering_best_practices.md`. `mart_platform_calibration_comparison` still builds to zero rows in CI, since its hardcoded outright-winner market IDs aren't in either platform's fixture, a known, documented gap, not an oversight.
