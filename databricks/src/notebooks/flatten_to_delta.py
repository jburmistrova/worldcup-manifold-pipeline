# Databricks notebook source
# COMMAND ----------
# MAGIC %md
# MAGIC # Spark: flatten raw JSON to Delta (bronze)
# MAGIC PySpark port of `spark/flatten_to_parquet.py` and `spark/flatten_polymarket.py`.
# MAGIC Same field selection and the same explicit-cast/optional-column guards
# MAGIC (`_as_double`, `_optional_string`) those two files needed for real,
# MAGIC found reasons -- schema inference from a small sample can guess the
# MAGIC wrong numeric type, or miss a column entirely, and both bugs are just as
# MAGIC real against Delta as they were against Parquet. Deliberately still
# MAGIC extract+load only, no business logic (ADR-0005): that stays in the
# MAGIC DLT staging/intermediate/marts layer, same division of labor as dbt had.
# MAGIC
# MAGIC Reads from the Unity Catalog Volume `ingest_manifold`/`ingest_polymarket`
# MAGIC land raw JSON into; writes managed Delta tables into `<catalog>.raw`,
# MAGIC the bronze layer the DLT pipeline's staging layer reads from next.

# COMMAND ----------
dbutils.widgets.text("catalog", "worldcup_manifold", "Catalog")
CATALOG = dbutils.widgets.get("catalog")
RAW_DIR = f"/Volumes/{CATALOG}/raw/landed_json"

# COMMAND ----------
from pyspark.sql.functions import col, explode, lit
from pyspark.sql.types import DoubleType, LongType, StringType

# `spark` is already provided by the Databricks notebook runtime -- no
# SparkSession.builder(...) needed here, unlike the local script this ports.


def _as_double(*names):
    return [col(n).cast(DoubleType()) for n in names]


def _as_double_aliased(*paths):
    # Polymarket flatten's own variant: cast() alone on a qualified path
    # (e.g. "m.volume") produces a column literally named
    # "CAST(m.volume AS DOUBLE)", not "volume" -- a real bug the original
    # flatten_polymarket.py caught by inspecting its output schema, not by
    # assuming an unaliased cast keeps a clean name.
    return [col(p).cast(DoubleType()).alias(p.split(".")[-1]) for p in paths]


def _optional_string(df, name):
    # Manifold only includes sportsStartTimestamp on ~1 in 6 real markets,
    # not present-but-null on the rest, absent from the payload entirely. A
    # small/uneven batch can leave Spark's inferred schema with no such
    # column at all; selecting it directly would then crash instead of
    # returning nulls.
    if name in df.columns:
        return col(name)
    return lit(None).cast(StringType())


# COMMAND ----------
# MAGIC %md ## Manifold: markets, market_answers, bets

# COMMAND ----------
def flatten_markets():
    df = spark.read.json(f"{RAW_DIR}/worldcup_2026_markets.jsonl")
    return df.select(
        "id", "question", "slug", "url", "outcomeType", "resolution",
        "isResolved",
        *_as_double("probability", "volume", "totalLiquidity"),
        "createdTime", "closeTime", "resolutionTime",
        _optional_string(df, "sportsStartTimestamp").alias("sportsStartTimestamp"),
    )


def flatten_market_answers():
    df = spark.read.json(f"{RAW_DIR}/worldcup_2026_market_answers.jsonl")
    return df.select(
        "contractId", "id", "index", "text", "isOther",
        *_as_double("probability", "resolutionProbability", "volume", "totalLiquidity"),
        "resolution", "resolutionTime", "createdTime",
    )


def flatten_bets():
    df = spark.read.json(f"{RAW_DIR}/worldcup_2026_bets.jsonl")
    return df.select(
        "id", "contractId", "answerId", "userId", "outcome",
        *_as_double("amount", "shares", "probBefore", "probAfter", "limitProb", "orderAmount"),
        "createdTime", "isFilled", "isCancelled", "isRedemption",
    )


# COMMAND ----------
# MAGIC %md ## Polymarket: markets (exploded from events), trades, prices

# COMMAND ----------
def flatten_polymarket_markets():
    df = spark.read.json(f"{RAW_DIR}/polymarket_2026_events.jsonl")
    exploded = df.select(
        col("id").alias("event_id"),
        col("title").alias("event_title"),
        explode("markets").alias("m"),
    )
    return exploded.select(
        col("m.id").alias("market_id"),
        col("m.conditionId").alias("condition_id"),
        col("m.question"),
        col("m.groupItemTitle"),
        col("m.negRiskMarketID").alias("neg_risk_market_id"),
        "event_id",
        "event_title",
        col("m.outcomes"),
        col("m.outcomePrices").alias("outcome_prices"),
        col("m.clobTokenIds").alias("clob_token_ids"),
        *_as_double_aliased("m.volume", "m.liquidity"),
        col("m.active"),
        col("m.closed"),
        col("m.createdAt").alias("created_at"),
        col("m.startDate").alias("start_date"),
        col("m.endDate").alias("end_date"),
        col("m.closedTime").alias("closed_time"),
    )


def flatten_polymarket_trades():
    df = spark.read.json(f"{RAW_DIR}/polymarket_2026_trades.jsonl")
    return df.select(
        "conditionId", "asset", "side", "outcome", "outcomeIndex",
        col("size").cast(DoubleType()),
        col("price").cast(DoubleType()),
        col("timestamp").cast(LongType()),
        "transactionHash",
    )


def flatten_polymarket_prices():
    df = spark.read.json(f"{RAW_DIR}/polymarket_2026_prices.jsonl")
    return df.select(
        "market_id", "condition_id", "token_id",
        col("t").cast(LongType()),
        col("p").cast(DoubleType()),
    )


# COMMAND ----------
jobs = [
    ("markets", flatten_markets),
    ("market_answers", flatten_market_answers),
    ("bets", flatten_bets),
    ("polymarket_markets", flatten_polymarket_markets),
    ("polymarket_trades", flatten_polymarket_trades),
    ("polymarket_prices", flatten_polymarket_prices),
]

counts = {}
for name, fn in jobs:
    df = fn()
    table = f"{CATALOG}.raw.{name}"
    df.write.mode("overwrite").saveAsTable(table)
    count = df.count()
    counts[name] = count
    print(f"{name}: {count} rows -> {table}")
    df.printSchema()

# COMMAND ----------
import json
dbutils.notebook.exit(json.dumps(counts))
