# Data Dictionary

## Format note

Raw ingestion writes **JSON Lines** (`data/raw/*.jsonl`) — one complete, unmodified API response object per line, not a hand-picked subset of fields. This project started with CSV and a curated field list; both choices turned out to be mistakes, documented in [ADR-0006](decisions/0006-raw-layer-jsonl-immutable.md). The tables below describe the fields Spark actually selects out of the full raw payload for `data/processed/*.parquet` — the raw JSONL files contain more fields than are listed here (e.g. `pool`, `mechanism`, `uniqueBettorCount` on markets), preserved as-is in case they're useful later, just not currently carried downstream.

## `data/raw/worldcup_2026_markets.jsonl` → `data/processed/markets`

Produced by [`ingest/pull_markets.py`](../ingest/pull_markets.py) — one JSON object per line, one per Manifold market matching the search term `"World Cup 2026"`. **389 rows** (current run — see note on non-determinism below).

| Field | Type | Notes |
|---|---|---|
| `id` | string | Manifold's internal market ID. |
| `question` | string | The market's title, e.g. "Will Norway defeat Senegal in the first round of World Cup 2026?" |
| `slug` | string | URL-safe identifier. |
| `url` | string | Returned directly by the API — the earlier CSV version reconstructed this manually from `creatorUsername` + `slug` because it seemed absent; capturing the full raw payload showed it was there all along. |
| `outcomeType` | string | `BINARY` (single yes/no probability), `MULTIPLE_CHOICE` (a set of sub-answers, each with its own probability — see caveat below), `MULTI_NUMERIC` (numeric-range answers), or `POLL` (no real-money resolution). Counts in this dataset: 210 `BINARY`, 166 `MULTIPLE_CHOICE`, 7 `MULTI_NUMERIC`, 6 `POLL`. |
| `isResolved` | bool | Whether the market has settled. Native JSON boolean — no string-parsing caveat needed (contrast with the CSV era, see History below). |
| `resolution` | string | **Meaning depends on `outcomeType`** — confirmed empirically, not assumed: for `BINARY`, one of `YES`, `NO`, `MKT` (resolved to a probability rather than a clean yes/no), or `CANCEL` (voided). For `MULTIPLE_CHOICE`, it's the **winning answer's ID** — not human-readable on its own. Prefer the per-answer `resolution` in the answers table below; it's already YES/NO. Empty until resolved. |
| `probability` | float, 0–1 | Current (or final, if resolved) implied probability. **Empty for `MULTIPLE_CHOICE` markets** — those carry probability per-answer. |
| `volume` | float | Cumulative trading volume in Mana (Manifold's play-money currency), not USD. |
| `totalLiquidity` | float | Size of the automated-market-maker's subsidy pool, in Mana — **not** the same as `volume` (turnover vs. AMM depth). Low-liquidity markets are noisier; a natural confidence weight for later calibration analysis. |
| `createdTime` | int | Unix epoch milliseconds, UTC. |
| `closeTime` | int | Same format — when betting closes on the market. |
| `resolutionTime` | int | Same format — empty until resolved. |

**Non-determinism, named plainly:** re-running this script won't necessarily return the identical set of markets. `/v0/search-markets` ranks by relevance, and that ranking isn't perfectly stable — confirmed across two real runs (388 unique markets after deduplicating one run, 389 on a fresh run shortly after). Small, expected, and worth being able to explain rather than being surprised by.

## `data/raw/worldcup_2026_market_answers.jsonl` → `data/processed/market_answers`

Produced by [`ingest/pull_market_answers.py`](../ingest/pull_market_answers.py) — for every market above whose `outcomeType` isn't `BINARY`, calls `GET /v0/market/{id}` and writes one line per answer in its `answers` array. `BINARY` markets are skipped — they already carry a single top-level probability/resolution. Each answer behaves like its own mini binary market. **3,286 rows**, from 179 non-BINARY markets (166 `MULTIPLE_CHOICE` + 7 `MULTI_NUMERIC` + 6 `POLL` = 179; 173 of them had at least one answer, 6 `POLL` markets had none).

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

## `data/raw/worldcup_2026_bets.jsonl` → `data/processed/bets`

Produced by [`ingest/pull_bets.py`](../ingest/pull_bets.py) — every bet object `GET /v0/bets` returns for every market above, paginated via the `after` bet-ID cursor. Deliberately unfiltered — filtering is dbt's job (`stg_manifold_bets`), not this script's, per [ADR-0005](decisions/0005-elt-not-etl-transformation-lives-in-dbt.md). **400,207 rows, zero duplicate bet IDs** — confirmed directly; the `after` cursor pagination used here doesn't share the offset-based instability that caused the markets duplication (see History below).

| Field | Type | Notes |
|---|---|---|
| `id` | string | Bet ID. |
| `contractId` | string | Foreign key to `id` in the markets table. |
| `userId` | string | The bettor. Not resolved to a username — not needed for this analysis. |
| `outcome` | string | `YES` or `NO` — which side this bet was on. |
| `amount` | float | Mana staked. Can be **negative** — redemptions (see below) show up as negative amounts. |
| `shares` | float | Shares bought/sold. |
| `probBefore` / `probAfter` | float, 0–1 | The market's implied probability immediately before and after this specific bet. **Core field for probability-over-time reconstruction** — ordering by `createdTime` and taking `probAfter` per bet gives the full price path. |
| `createdTime` | int | Epoch ms UTC. |
| `isFilled` | bool | Whether the bet actually executed. `false` for limit orders still resting unfilled. **Absent entirely** (not `false` — the key doesn't exist) on redemption records. |
| `isCancelled` | bool | Whether a limit order was cancelled before filling. |
| `isRedemption` | bool | Share redemptions (opposing YES/NO positions held by the same user cancelling out for a payout) — **not a real trade**. `probBefore == probAfter` on every redemption checked; they don't move the market. |
| `limitProb` | float, 0–1 | The limit price requested, only present on limit orders. |
| `orderAmount` | float | The amount requested for a limit order, which may differ from `amount` (the amount actually filled). |

**Critical filtering caveat, confirmed on the final data:** of 400,207 total rows, only **134,331 (33.6%)** are real, filled, non-cancelled trades. **137,661 (34.4%)** are cancelled/unfilled limit orders that never executed. **128,060 (32.0%)** are redemptions with zero price impact — confirmed directly (`probBefore == probAfter` on every redemption checked). A naive `AVG(probAfter)` or VWAP over the raw file would be badly wrong; two-thirds of it is noise for reconstructing what the market actually believed at each point in time. The correct filter for "real trade" is `isFilled = true AND isCancelled = false`. This logic belongs in `stg_manifold_bets`, tested there, not silently baked into ingestion.

## History: the CSV era (superseded by ADR-0006, not deleted)

The project started with CSV as the raw format, with real, instructive consequences — kept here rather than erased, since they're genuinely useful "what broke" material:

- **A text field with a nested quoted phrase** (`"Shocking decision, Ref!": ...`) caused Spark's CSV parser to mis-split the row at an internal comma, shifting every column after it by one. Python's own `csv` module parsed it correctly; Spark's didn't, by default.
- **Three markets had a literal newline embedded in `question`.** Spark's default (non-`multiLine`) CSV reader treated each as two physical rows, inflating the market count by exactly 3.
- **A pagination-instability bug produced 63 duplicate markets**, which cascaded into 128 duplicate answers and 5,391 duplicate bets — a real bug, unrelated to the file format, but the fix was first applied incorrectly (overwriting raw CSVs in place, destroying the original snapshot) before being corrected properly.

All three are exactly why the raw format changed to JSON Lines and why raw data is now treated as immutable — full reasoning in [ADR-0006](decisions/0006-raw-layer-jsonl-immutable.md). The original CSVs (as they stood after the in-place dedup, not the true original) are archived at `data/archive/csv_v1/`, not deleted.

## Open questions / not yet handled

- None currently blocking. All three raw files are ingested via the JSON pipeline, deduplicated correctly, and flattened to Parquet with real native types. Next real work is on the transformation side: `stg_manifold_bets`'s filter logic and its test coverage, in dbt.
