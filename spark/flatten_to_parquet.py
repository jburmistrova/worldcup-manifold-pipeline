"""Spark extract+load step: read the raw JSON Lines ingestion files, select
the fields this project actually needs, write Parquet. No business logic
(no probability reconstruction, no VWAP, no repricing detection, that's
dbt's job per ADR-0005).

Unlike the earlier CSV-based version of this script, JSON carries real
native types (booleans are actual booleans, numbers are actual numbers), so
there's no defensive string-then-cast dance here. That entire class of
problem (see ADR-0006) doesn't exist for a properly-typed source format.

Correcting an earlier claim in this docstring: "schema inference is safe
because JSON is self-describing." Per-value, yes, but Spark's schema
*inference* still guesses a column's type from a sample of the actual data,
not from any fixed contract, and that guess can differ across samples. Found
for real, not hypothetically: on the small CI fixture (tests/fixtures/raw/),
every totalLiquidity value happens to be a whole number, so Spark inferred
BIGINT; on the full dataset, fractional values (e.g. 142.857...) make it
infer DOUBLE. Same field, same source, different inferred type depending
on which rows happened to be in the sample. That silently broke
mart_market_efficiency's enforced contract (data_type: double) the first
time CI ran against the fixture. Fixed by casting every real-valued
business field explicitly instead of trusting inference for them. The
type is now guaranteed regardless of what a given sample happens to contain.
"""
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, lit
from pyspark.sql.types import DoubleType, StringType

RAW_DIR = "data/raw"
OUT_DIR = "data/processed"


def _as_double(*names):
    # forces a real-valued business field to DOUBLE regardless of what
    # Spark's schema inference guessed from the sample it happened to see
    return [col(n).cast(DoubleType()) for n in names]


def _optional_string(df, name):
    # Manifold only includes this field on some markets at all (see
    # ADR-0008): sportsStartTimestamp is present on ~1 in 6 real markets,
    # not present-but-null on the rest, absent from the payload entirely.
    # A small sample (the CI fixture's 5 markets, by chance none of the
    # qualifying shape) can end up with zero rows carrying the key, and
    # Spark's inferred schema then has no such column at all, not a
    # nullable one. Selecting it directly crashes with an unresolved-column
    # error instead of returning nulls. Same root cause as _as_double
    # above (a small sample's inferred schema can't be trusted to match the
    # full dataset's), one level earlier: here it's the column's existence,
    # not just its type, that a small sample can get wrong.
    if name in df.columns:
        return col(name)
    return lit(None).cast(StringType())


def flatten_markets(spark):
    df = spark.read.json(f"{RAW_DIR}/worldcup_2026_markets.jsonl")
    return df.select(
        "id", "question", "slug", "url", "outcomeType", "resolution",
        "isResolved",
        *_as_double("probability", "volume", "totalLiquidity"),
        "createdTime", "closeTime", "resolutionTime",
        # present on 108 of 621 markets (sports-integrated markets only,
        # see ADR-0008), a real precise kickoff time straight from Manifold.
        # Was flagged as "not carried into Parquet yet" in data_dictionary.md;
        # now that it drives real matching logic, it needs to be here.
        _optional_string(df, "sportsStartTimestamp").alias("sportsStartTimestamp"),
    )


def flatten_market_answers(spark):
    df = spark.read.json(f"{RAW_DIR}/worldcup_2026_market_answers.jsonl")
    return df.select(
        "contractId", "id", "index", "text", "isOther",
        *_as_double("probability", "resolutionProbability", "volume", "totalLiquidity"),
        "resolution", "resolutionTime", "createdTime",
    )


def flatten_bets(spark):
    # answerId: present (a real id) on multi-choice-market bets, entirely absent
    # (not just null) on binary-market bets. Each answer has its own independent
    # probability track, so this is required to correctly group bets by which
    # probability stream they belong to. Missing from the original field list;
    # added after checking the raw payload directly rather than assuming.
    df = spark.read.json(f"{RAW_DIR}/worldcup_2026_bets.jsonl")
    return df.select(
        "id", "contractId", "answerId", "userId", "outcome",
        *_as_double("amount", "shares", "probBefore", "probAfter", "limitProb", "orderAmount"),
        "createdTime", "isFilled", "isCancelled", "isRedemption",
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
