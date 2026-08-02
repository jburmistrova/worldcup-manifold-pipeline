"""Loads Spark's flattened Parquet output into real Postgres tables, only
needed when the postgres dbt target is in use (see ADR-0004).

DuckDB reads the same Parquet files directly (dbt/models/staging/_sources.yml's
external_location), no separate load step. Postgres has no equivalent way to
query a Parquet file in place, so this exists specifically to make that
target work at all, not to duplicate work DuckDB already avoids. The default
DuckDB path never runs this.
"""
import io
import os

import pandas as pd
import pyarrow.parquet as pq
from sqlalchemy import Boolean, create_engine

PROCESSED_DIR = "data/processed"
SCHEMA = "raw"
TABLES = ["markets", "market_answers", "bets"]


def _boolean_columns(table_dir):
    # Parquet's own schema is the authoritative source for a column's real
    # type, unlike pandas' post-hoc dtype inference. isFilled/isCancelled
    # (see stg_manifold_bets) have real nulls mixed with True/False; a
    # native numpy bool array can't hold nulls, so pandas silently falls
    # back to generic 'object' dtype, indistinguishable from a genuine
    # string column by dtype alone. Left to guess from that, to_sql()
    # would create a text column instead of boolean.
    schema = pq.ParquetDataset(table_dir).schema
    return {schema.field(i).name for i in range(len(schema)) if str(schema.field(i).type) == "bool"}


def _load_table(engine, df, table, schema, bool_columns):
    # pandas' own row-by-row to_sql() is fine for markets/market_answers
    # (thousands of rows) but genuinely too slow for bets (1.17M+ rows on
    # the full dataset): minutes of individual INSERTs for a bulk load.
    # to_sql() here only creates the table (0 rows, so schema/types come
    # from the DataFrame's dtypes, not from any data, with an explicit
    # override for the boolean columns pandas' dtype inference gets wrong),
    # then Postgres' own COPY does the actual bulk load, the right tool for
    # this volume, not a premature optimization. CSV's default NULL
    # representation is an unquoted empty string, which is exactly what
    # to_csv() already writes for NaN/None, so no special-casing is needed
    # there.
    dtype_overrides = {col: Boolean for col in bool_columns if col in df.columns}
    df.head(0).to_sql(
        table, engine, schema=schema, if_exists="replace", index=False,
        dtype=dtype_overrides,
    )

    buf = io.StringIO()
    df.to_csv(buf, index=False, header=False)
    buf.seek(0)

    raw_conn = engine.raw_connection()
    try:
        with raw_conn.cursor() as cur:
            cur.copy_expert(f"COPY {schema}.{table} FROM STDIN WITH CSV", buf)
        raw_conn.commit()
    finally:
        raw_conn.close()


def main():
    url = (
        f"postgresql+psycopg2://{os.environ['POSTGRES_USER']}:{os.environ['POSTGRES_PASSWORD']}"
        f"@{os.environ.get('POSTGRES_HOST', 'localhost')}:{os.environ.get('POSTGRES_PORT', '5432')}"
        f"/{os.environ.get('POSTGRES_DB', 'worldcup')}"
    )
    engine = create_engine(url)

    with engine.begin() as conn:
        conn.exec_driver_sql(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    for table in TABLES:
        table_dir = f"{PROCESSED_DIR}/{table}"
        bool_columns = {c.lower() for c in _boolean_columns(table_dir)}

        df = pd.read_parquet(table_dir)
        # Postgres folds every unquoted identifier to lowercase, including
        # in the dbt staging SQL that already references these columns
        # unquoted (contractId, sportsStartTimestamp, isFilled, ...).
        # to_sql() would otherwise create genuinely mixed-case, quoted
        # columns from the DataFrame's real names, which an unquoted
        # reference can never match. DuckDB isn't affected: it reads these
        # same Parquet files directly, case as-is, no separate load step.
        df.columns = [c.lower() for c in df.columns]
        _load_table(engine, df, table, SCHEMA, bool_columns)
        print(f"{table}: {len(df)} rows -> postgres schema '{SCHEMA}'")


if __name__ == "__main__":
    main()
