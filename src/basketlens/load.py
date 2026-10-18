"""Convert the raw R files to Parquet and build the DuckDB warehouse.

    python -m basketlens.load [--raw data/raw] [--db data/warehouse.duckdb]

Raw tables are loaded as they are. All derived tables (clean lines, ranging, promotion flags) are built by
sql/01_warehouse.sql, which is plain SQL that also runs on Snowflake with the COPY INTO / CREATE TABLE changes in
docs/SNOWFLAKE.md.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import duckdb
import pandas as pd
import pyreadr

from .sqlrun import run_file

RAW_TABLES = {
    "transactions": "rds", "promotions": "rds", "products": "rda", "demographics": "rda", "campaigns": "rda",
    "campaign_descriptions": "rda", "coupons": "rda", "coupon_redemptions": "rda",
}


def read_r(raw: Path, name: str) -> pd.DataFrame:
    res = pyreadr.read_r(str(raw / f"{name}.{RAW_TABLES[name]}"))
    df = next(iter(res.values()))
    for c in df.columns:  # categoricals -> plain strings so SQL sees VARCHAR
        if isinstance(df[c].dtype, pd.CategoricalDtype):
            df[c] = df[c].astype("string")
    return df


def to_parquet(raw: Path, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for name in RAW_TABLES:
        p = out / f"{name}.parquet"
        if p.exists():
            continue
        df = read_r(raw, name)
        df.to_parquet(p, index=False)
        print(f"{name}: {len(df):,} rows")


def build(raw: Path, db: Path, parquet: Path | None = None) -> duckdb.DuckDBPyConnection:
    parquet = parquet or raw.parent / "parquet"
    to_parquet(raw, parquet)
    return build_from_parquet(parquet, db)


def build_from_parquet(parquet: Path, db: Path) -> duckdb.DuckDBPyConnection:
    """Build the warehouse from Parquet files named like the raw tables (used for the real data and for the twin)."""
    if db.exists():
        db.unlink()
    con = duckdb.connect(str(db))
    for name in RAW_TABLES:
        con.execute(f"CREATE TABLE raw_{name} AS SELECT * FROM read_parquet('{(parquet / (name + '.parquet')).as_posix()}')")
    run_file(con, "01_warehouse.sql")
    return con


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default="data/raw")
    ap.add_argument("--db", default="data/warehouse.duckdb")
    a = ap.parse_args()
    con = build(Path(a.raw), Path(a.db))
    for t in ("fact_line", "dim_product", "dim_household", "ranging", "promo_week", "campaign"):
        print(t, con.execute(f"SELECT count(*) FROM {t}").fetchone()[0])


if __name__ == "__main__":
    main()
