"""Spark extract+load step for Polymarket's raw data, mirroring
flatten_to_parquet.py's role for Manifold (ADR-0005: no business logic here,
that's dbt's job). A separate script, not a shared one, because the raw
shapes are genuinely different: Polymarket's markets arrive nested inside
events (explode, not select), and there's a third dataset (prices) Manifold
has no equivalent of at all.
"""
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, explode
from pyspark.sql.types import DoubleType, LongType

RAW_DIR = "data/raw"
OUT_DIR = "data/processed"


def _as_double(*paths):
    # same helper as flatten_to_parquet.py's own, forcing a real-valued
    # field to DOUBLE regardless of what Spark's schema inference guessed,
    # and aliasing it back to its plain (unqualified) name: cast() alone
    # produces a column literally named "CAST(m.field AS DOUBLE)", not the
    # field name, a real bug caught by inspecting the actual output schema
    # rather than assuming an unaliased cast keeps a clean name.
    return [col(p).cast(DoubleType()).alias(p.split(".")[-1]) for p in paths]


def flatten_polymarket_markets(spark):
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
        *_as_double("m.volume", "m.liquidity"),
        col("m.active"),
        col("m.closed"),
        col("m.createdAt").alias("created_at"),
        col("m.startDate").alias("start_date"),
        col("m.endDate").alias("end_date"),
        col("m.closedTime").alias("closed_time"),
    )


def flatten_polymarket_trades(spark):
    df = spark.read.json(f"{RAW_DIR}/polymarket_2026_trades.jsonl")
    return df.select(
        "conditionId", "asset", "side", "outcome", "outcomeIndex",
        col("size").cast(DoubleType()),
        col("price").cast(DoubleType()),
        col("timestamp").cast(LongType()),
        "transactionHash",
    )


def flatten_polymarket_prices(spark):
    df = spark.read.json(f"{RAW_DIR}/polymarket_2026_prices.jsonl")
    return df.select(
        "market_id", "condition_id", "token_id",
        col("t").cast(LongType()),
        col("p").cast(DoubleType()),
    )


def main():
    spark = SparkSession.builder.appName("flatten-polymarket-to-parquet").master("local[*]").getOrCreate()
    spark.sparkContext.setLogLevel("WARN")

    jobs = [
        ("polymarket_markets", flatten_polymarket_markets),
        ("polymarket_trades", flatten_polymarket_trades),
        ("polymarket_prices", flatten_polymarket_prices),
    ]

    for name, fn in jobs:
        df = fn(spark)
        out_path = f"{OUT_DIR}/{name}"
        df.write.mode("overwrite").parquet(out_path)
        count = df.count()
        print(f"{name}: {count} rows -> {out_path}")
        df.printSchema()

    spark.stop()


if __name__ == "__main__":
    main()
