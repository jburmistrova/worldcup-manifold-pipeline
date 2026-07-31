"""Spark extract+load step: read the raw JSON Lines ingestion files, select
the fields this project actually needs, write Parquet. No business logic
(no probability reconstruction, no VWAP, no repricing detection — that's
dbt's job per ADR-0005).

Unlike the earlier CSV-based version of this script, JSON carries real
native types (booleans are actual booleans, numbers are actual numbers), so
there's no defensive string-then-cast dance here — that entire class of
problem (see ADR-0006) doesn't exist for a properly-typed source format.
Schema inference is safe here specifically because JSON is self-describing,
unlike CSV where every field is ambiguous text.
"""
from pyspark.sql import SparkSession

RAW_DIR = "data/raw"
OUT_DIR = "data/processed"


def flatten_markets(spark):
    df = spark.read.json(f"{RAW_DIR}/worldcup_2026_markets.jsonl")
    return df.select(
        "id", "question", "slug", "url", "outcomeType", "resolution",
        "isResolved", "probability", "volume", "totalLiquidity",
        "createdTime", "closeTime", "resolutionTime",
    )


def flatten_market_answers(spark):
    df = spark.read.json(f"{RAW_DIR}/worldcup_2026_market_answers.jsonl")
    return df.select(
        "contractId", "id", "index", "text", "isOther",
        "probability", "resolution", "resolutionProbability", "resolutionTime",
        "volume", "totalLiquidity", "createdTime",
    )


def flatten_bets(spark):
    # answerId: present (a real id) on multi-choice-market bets, entirely absent
    # (not just null) on binary-market bets — each answer has its own independent
    # probability track, so this is required to correctly group bets by which
    # probability stream they belong to. Missing from the original field list;
    # added after checking the raw payload directly rather than assuming.
    df = spark.read.json(f"{RAW_DIR}/worldcup_2026_bets.jsonl")
    return df.select(
        "id", "contractId", "answerId", "userId", "outcome", "amount", "shares",
        "probBefore", "probAfter", "createdTime",
        "isFilled", "isCancelled", "isRedemption", "limitProb", "orderAmount",
    )


def main():
    spark = SparkSession.builder.appName("flatten-to-parquet").master("local[*]").getOrCreate()
    spark.sparkContext.setLogLevel("WARN")

    jobs = [
        ("markets", flatten_markets),
        ("market_answers", flatten_market_answers),
        ("bets", flatten_bets),
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
