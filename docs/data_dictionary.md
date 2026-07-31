# Data Dictionary

## Format note

Raw ingestion writes **JSON Lines** (`data/raw/*.jsonl`) — one complete, unmodified API response object per line, not a hand-picked subset of fields. This project started with CSV and a curated field list; both choices turned out to be mistakes, documented in [ADR-0006](decisions/0006-raw-layer-jsonl-immutable.md). The tables below describe the fields Spark actually selects out of the full raw payload for `data/processed/*.parquet` — the raw JSONL files contain more fields than are listed here (e.g. `pool`, `mechanism`, `uniqueBettorCount` on markets), preserved as-is in case they're useful later, just not currently carried downstream. Each section also has a `→ dbt` table mapping that Parquet column to its renamed, typed dbt staging column. Naming convention in brief: `_id` for identifiers, `_at` for real timestamps (converted from raw epoch-ms, not left as integers under a misleading name), `is_`/`has_` for booleans, and family-word-first grouping for fields that share a concept (`prob_before`/`prob_after`/`prob_limit`, `amount`/`amount_order`) so related columns sort and browse together.

## `data/raw/worldcup_2026_markets.jsonl` → `data/processed/markets`

Produced by [`ingest/pull_markets.py`](../ingest/pull_markets.py) — one JSON object per line, one per Manifold market matching the search term `"World Cup 2026"`. **621 rows.** A prior version of this script found only 389 — 232 real markets were silently missing due to a pagination bug, found and fixed in [ADR-0007](decisions/0007-search-limit-truncation.md).

| Field | Type | Notes |
|---|---|---|
| `id` | string | Manifold's internal market ID. |
| `question` | string | The market's title, e.g. "Will Norway defeat Senegal in the first round of World Cup 2026?" |
| `slug` | string | URL-safe identifier. |
| `url` | string | Returned directly by the API — the earlier CSV version reconstructed this manually from `creatorUsername` + `slug` because it seemed absent; capturing the full raw payload showed it was there all along. |
| `outcomeType` | string | `BINARY` (single yes/no probability), `MULTIPLE_CHOICE` (a set of sub-answers, each with its own probability — see caveat below), `MULTI_NUMERIC` (numeric-range answers), or `POLL` (no real-money resolution). Counts in this dataset: 335 `MULTIPLE_CHOICE`, 271 `BINARY`, 9 `MULTI_NUMERIC`, 6 `POLL`. |
| `isResolved` | bool | Whether the market has settled. Native JSON boolean — no string-parsing caveat needed (contrast with the CSV era, see History below). |
| `resolution` | string | **Meaning depends on `outcomeType`** — confirmed empirically, not assumed: for `BINARY`, one of `YES`, `NO`, `MKT` (resolved to a probability rather than a clean yes/no), or `CANCEL` (voided). For `MULTIPLE_CHOICE`, it's the **winning answer's ID** — not human-readable on its own. Prefer the per-answer `resolution` in the answers table below; it's already YES/NO. Empty until resolved. |
| `probability` | float, 0–1 | Current (or final, if resolved) implied probability. **Empty for `MULTIPLE_CHOICE` markets** — those carry probability per-answer. |
| `volume` | float | Cumulative trading volume in Mana (Manifold's play-money currency), not USD. |
| `totalLiquidity` | float | Size of the automated-market-maker's subsidy pool, in Mana — **not** the same as `volume` (turnover vs. AMM depth). Low-liquidity markets are noisier; a natural confidence weight for later calibration analysis. |
| `createdTime` | int | Unix epoch milliseconds, UTC. |
| `closeTime` | int | Same format — when betting closes on the market. Not a reliable proxy for match kickoff time — verified against a market whose question stated an exact date, `closeTime` was set to a round "end of day" value, and `resolutionTime` for the same market lagged 4 days behind it. |
| `resolutionTime` | int | Same format — empty until resolved. |
| `sportsStartTimestamp` | string (ISO 8601) | **Not carried into Parquet yet** — flagging its existence here since it's genuinely useful and easy to miss. Present on 108 of 621 markets (sports-integrated markets specifically) — a real, precise match kickoff time, e.g. `"2026-06-30T01:00:00Z"`. Found while investigating whether a true pre-kickoff calibration analysis was possible; see [ADR-0007](decisions/0007-search-limit-truncation.md). Only covers ~17% of markets, so useful for a targeted stretch analysis, not a full-dataset one. |

**Non-determinism, named plainly:** re-running this script won't necessarily return the identical set of markets, since `/v0/search-markets` ranks by relevance and new markets can appear. Confirmed small (single-digit) variation across same-`limit` runs — the 232-market discrepancy found and documented in ADR-0007 was a real bug (`limit` too small), not this kind of ordinary variation.

### → `stg_manifold_markets` (dbt)

Pure rename + type conversion, no rows dropped, no filtering — every market from the source is included.

| Raw (Parquet) | dbt staging column | Notes |
|---|---|---|
| `id` | `market_id` | |
| `question` | `question` | |
| `slug` | `slug` | |
| `url` | `url` | |
| `outcomeType` | `outcome_type` | |
| `resolution` | `resolution` | |
| `isResolved` | `is_resolved` | |
| `probability` | `prob` | abbreviated to match `prob_before`/`prob_after`/`prob_limit` in `stg_manifold_bets` — same concept, same name, across every table |
| `volume` | `volume` | |
| `totalLiquidity` | `liquidity_total` | family-word-first: `liquidity` is the concept, `total` the modifier |
| `createdTime` | `created_at` | epoch-ms int → real `TIMESTAMP`, via DuckDB's `epoch_ms()` |
| `closeTime` | `closed_at` | same conversion |
| `resolutionTime` | `resolved_at` | same conversion |

## `data/raw/worldcup_2026_market_answers.jsonl` → `data/processed/market_answers`

Produced by [`ingest/pull_market_answers.py`](../ingest/pull_market_answers.py) — for every market above whose `outcomeType` isn't `BINARY`, calls `GET /v0/market/{id}` and writes one line per answer in its `answers` array. `BINARY` markets are skipped — they already carry a single top-level probability/resolution. Each answer behaves like its own mini binary market. **4,545 rows**, from 350 non-BINARY markets (335 `MULTIPLE_CHOICE` + 9 `MULTI_NUMERIC` + 6 `POLL` = 350; 344 of them had at least one answer, 6 `POLL` markets had none).

| Field | Type | Notes |
|---|---|---|
| `contractId` | string | Foreign key to `id` in the markets table. A market has many answers. |
| `id` | string | This answer's own ID — the value that shows up as the parent market's top-level `resolution` for `MULTIPLE_CHOICE` markets. |
| `index` | int | Display order of the answer within the market (0-based). |
| `text` | string | Human-readable answer label, e.g. "Lionel Messi to score at least one goal." |
| `isOther` | bool | Whether this is Manifold's auto-generated catch-all "Other" answer. |
| `probability` | float, 0–1 | Current (or final) probability for this specific answer. |
| `resolution` | string | `YES` / `NO` for this answer specifically, or empty if unresolved — already human-readable, no ID to decode. |
| `resolutionProbability` | float, 0–1 | The probability at the moment this answer resolved — the key input for the market-calibration mart later. |
| `resolutionTime` | int | Epoch ms UTC. |
| `volume` | float | Trading volume in Mana, scoped to this answer. |
| `totalLiquidity` | float | AMM liquidity pool depth, scoped to this answer. |
| `createdTime` | int | Epoch ms UTC. |

### → `stg_manifold_market_answers` (dbt)

Pure rename + type conversion, no rows dropped.

| Raw (Parquet) | dbt staging column | Notes |
|---|---|---|
| `contractId` | `market_id` | renamed to match — every staging table uses the same join-key name, which is what let the earlier cross-table join work with zero friction |
| `id` | `answer_id` | `id` alone would collide/confuse once joined against `market_id` |
| `index` | `answer_index` | same reason — explicit about which entity it belongs to |
| `text` | `answer_text` | |
| `isOther` | `is_other` | |
| `probability` | `prob` | |
| `resolution` | `resolution` | |
| `resolutionProbability` | `prob_resolution` | groups alphabetically with `prob` |
| `volume` | `volume` | |
| `totalLiquidity` | `liquidity_total` | |
| `createdTime` | `created_at` | epoch-ms → `TIMESTAMP` |
| `resolutionTime` | `resolved_at` | epoch-ms → `TIMESTAMP` |

## `data/raw/worldcup_2026_bets.jsonl` → `data/processed/bets`

Produced by [`ingest/pull_bets.py`](../ingest/pull_bets.py) — every bet object `GET /v0/bets` returns for every market above, paginated via the `after` bet-ID cursor. Deliberately unfiltered — filtering is dbt's job (`stg_manifold_bets`), not this script's, per [ADR-0005](decisions/0005-elt-not-etl-transformation-lives-in-dbt.md). **1,176,547 rows, zero duplicate bet IDs** — confirmed directly; the `after` cursor pagination used here doesn't share the offset-based instability that caused the markets truncation/duplication bugs ([ADR-0006](decisions/0006-raw-layer-jsonl-immutable.md), [ADR-0007](decisions/0007-search-limit-truncation.md)).

| Field | Type | Notes |
|---|---|---|
| `id` | string | Bet ID. |
| `contractId` | string | Foreign key to `id` in the markets table. |
| `userId` | string | The bettor. Not resolved to a username — not needed for this analysis. |
| `outcome` | string | `YES` or `NO` — which side this bet was on. |
| `amount` | float | Mana staked. **Can be negative for two different reasons, confirmed separately, not assumed:** redemptions (see below) are always negative, but so are genuine **sell trades** — unwinding an existing position back into the pool. Sells are real, price-moving activity (`probBefore != probAfter`, unlike redemptions) and correctly remain in `stg_manifold_bets` after filtering. A buy's `amount` is usually round (a human typed a stake into the bet box); a sell's is essentially never round, same reason `shares` isn't — both are computed by the AMM's pricing curve at that moment, not chosen by a person. |
| `shares` | float | Shares bought/sold. Almost never a round number — derived from the AMM's pricing curve given the market's state at that instant, not user input (contrast with `amount` on a buy, which usually *is* round, since that's what the user actually typed). |
| `probBefore` / `probAfter` | float, 0–1 | The market's implied probability immediately before and after this specific bet. **Core field for probability-over-time reconstruction** — ordering by `createdTime` and taking `probAfter` per bet gives the full price path. |
| `createdTime` | int | Epoch ms UTC. |
| `isFilled` | bool | Whether the bet actually executed. `false` for limit orders still resting unfilled. **Absent entirely** (not `false` — the key doesn't exist) on redemption records. |
| `isCancelled` | bool | Whether a limit order was cancelled before filling. |
| `isRedemption` | bool | Share redemptions (opposing YES/NO positions held by the same user cancelling out for a payout) — **not a real trade**. `probBefore == probAfter` on every redemption checked; they don't move the market. |
| `limitProb` | float, 0–1 | The limit price requested, only present on limit orders. |
| `orderAmount` | float | The amount requested for a limit order, which may differ from `amount` (the amount actually filled). |

**Critical filtering caveat, confirmed on the final data:** of 1,176,547 total rows, only **212,749 (18.1%)** are real trades. **758,308 (64.5%)** are cancelled/unfilled limit orders that never executed. **203,258 (17.3%)** are redemptions with zero price impact — confirmed directly (`probBefore == probAfter` on every redemption checked). **1,367 (0.1%)** are zero-amount "seeding" events — multiple rows sharing the exact same timestamp, `probBefore == probAfter`, appearing at market/answer creation, read as a system-generated initial share allocation rather than a real trade. Caught because it broke a downstream calculation (`0 / 0` in a running VWAP produced `NaN`, which a bounds test then flagged), not by inspection — a good example of a test earning its keep. Worth noting the proportions shifted noticeably after [ADR-0007](decisions/0007-search-limit-truncation.md)'s fix recovered 232 previously-missing markets (real-trade share dropped from ~33% to ~18%, cancelled share rose from ~34% to ~65%) — the newly-recovered markets, several of them high-volume sports-linked or mega prop-bet markets, apparently carry a lot more limit-order/cancelled-order activity than the smaller markets in the original, incomplete dataset. A naive `AVG(probAfter)` or VWAP over the raw file would be badly wrong — over 80% of it is noise for reconstructing what the market actually believed at each point in time. The correct filter for "real trade" is `isFilled = true AND isCancelled = false AND amount != 0`. This logic belongs in `stg_manifold_bets`, tested there, not silently baked into ingestion.

### → `stg_manifold_bets` (dbt)

**Not a pure rename** — this is the one staging model that also filters rows. `WHERE isFilled = true AND isCancelled = false AND amount != 0` drops the ~81.9% of rows that are cancelled/unfilled orders, redemptions, or zero-amount seeding events, per the caveat above. 1,176,547 raw rows → 212,749 staged rows.

| Raw (Parquet) | dbt staging column | Notes |
|---|---|---|
| `id` | `bet_id` | |
| `contractId` | `market_id` | |
| `answerId` | `answer_id` | present (a real id) on `MULTIPLE_CHOICE`-market bets, absent (not just null) on `BINARY`-market bets — each answer has its own independent probability track. Missing from the original field list; added after checking the raw payload directly while designing `int_market_implied_probability`, not assumed present. |
| `userId` | `user_id` | |
| `outcome` | `outcome` | |
| `amount` | `amount` | |
| `orderAmount` | `amount_order` | family-word-first, groups with `amount` |
| `shares` | `count_share` | `count` as the family word — anticipates other count-type fields later (e.g. the raw `uniqueBettorCount` field on markets, not yet carried through, would become `count_bettor` under the same convention) |
| `probBefore` | `prob_before` | |
| `probAfter` | `prob_after` | |
| `limitProb` | `prob_limit` | |
| `createdTime` | `created_at` | epoch-ms → `TIMESTAMP` |
| `isFilled` | `is_filled` | also drives the `WHERE` filter above |
| `isCancelled` | `is_cancelled` | also drives the `WHERE` filter above |
| `isRedemption` | `is_redemption` | |

## History: the CSV era (superseded by ADR-0006, not deleted)

The project started with CSV as the raw format, with real, instructive consequences — kept here rather than erased, since they're genuinely useful "what broke" material:

- **A text field with a nested quoted phrase** (`"Shocking decision, Ref!": ...`) caused Spark's CSV parser to mis-split the row at an internal comma, shifting every column after it by one. Python's own `csv` module parsed it correctly; Spark's didn't, by default.
- **Three markets had a literal newline embedded in `question`.** Spark's default (non-`multiLine`) CSV reader treated each as two physical rows, inflating the market count by exactly 3.
- **A pagination-instability bug produced 63 duplicate markets**, which cascaded into 128 duplicate answers and 5,391 duplicate bets — a real bug, unrelated to the file format, but the fix was first applied incorrectly (overwriting raw CSVs in place, destroying the original snapshot) before being corrected properly.

All three are exactly why the raw format changed to JSON Lines and why raw data is now treated as immutable — full reasoning in [ADR-0006](decisions/0006-raw-layer-jsonl-immutable.md). The original CSVs (as they stood after the in-place dedup, not the true original) are archived at `data/archive/csv_v1/`, not deleted.

## Open questions / not yet handled

- None currently blocking. All three raw files are ingested via the JSON pipeline, deduplicated correctly, and flattened to Parquet with real native types. Next real work is on the transformation side: `stg_manifold_bets`'s filter logic and its test coverage, in dbt.
