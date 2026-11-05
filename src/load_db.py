"""
Load data/processed/prices_clean.csv into a SQLite star schema
(data/kenya_food_prices.db) and run every query in sql/analysis_queries.sql,
saving each result to reports/sql_results/<query_name>.csv.

Queries in the .sql file are separated by a header comment of the form
    -- name: <query_name>

Usage:
    python src/load_db.py
"""
import re
import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "data" / "processed" / "prices_clean.csv"
DB = ROOT / "data" / "kenya_food_prices.db"
SCHEMA = ROOT / "sql" / "schema.sql"
QUERIES = ROOT / "sql" / "analysis_queries.sql"
RESULTS = ROOT / "reports" / "sql_results"

ASAL_COUNTIES = {"Turkana", "Marsabit", "Mandera", "Garissa", "Kitui", "Wajir", "Isiolo", "Samburu",
                 "Baringo", "West Pokot", "Tana River", "Kajiado", "Makueni", "Laikipia", "Narok"}


def load(con: sqlite3.Connection) -> None:
    df = pd.read_csv(CLEAN, parse_dates=["date"])
    con.executescript(SCHEMA.read_text())

    markets = (df.groupby("market", as_index=False)
                 .agg(county=("admin2", "first"), region=("admin1", "first"),
                      latitude=("latitude", "first"), longitude=("longitude", "first")))
    markets["zone"] = markets["county"].map(lambda c: "ASAL" if c in ASAL_COUNTIES else "High-potential")
    markets.insert(0, "market_id", range(1, len(markets) + 1))
    markets[["market_id", "market", "county", "region", "zone", "latitude", "longitude"]].to_sql(
        "dim_market", con, if_exists="append", index=False)

    comms = df.groupby("commodity", as_index=False).agg(category=("category", "first"), unit=("unit", "first"))
    comms.insert(0, "commodity_id", range(1, len(comms) + 1))
    comms.to_sql("dim_commodity", con, if_exists="append", index=False)

    fx = (df.assign(r=df["price"] / df["usdprice"]).groupby("date")["r"].median().round(2)
            .rename("kes_per_usd").reset_index().rename(columns={"date": "month"}))
    fx["month"] = fx["month"].dt.strftime("%Y-%m-%d")
    fx.to_sql("dim_fx", con, if_exists="append", index=False)

    fact = (df.merge(markets[["market", "market_id"]], on="market")
              .merge(comms[["commodity", "commodity_id"]], on="commodity"))
    fact = fact.drop(columns=["year", "month"]).rename(columns={"date": "month", "pricetype": "price_type", "price": "price_kes", "usdprice": "price_usd"})
    fact["month"] = fact["month"].dt.strftime("%Y-%m-%d")
    fact[["month", "market_id", "commodity_id", "price_type", "price_kes", "price_usd"]].to_sql(
        "fact_price", con, if_exists="append", index=False)
    con.commit()
    print(f"Loaded {len(fact):,} price rows, {len(markets)} markets, {len(comms)} commodities into {DB.name}")


def run_queries(con: sqlite3.Connection) -> dict[str, pd.DataFrame]:
    text = QUERIES.read_text()
    blocks = re.split(r"^-- name:\s*(\w+)\s*$", text, flags=re.M)[1:]
    RESULTS.mkdir(parents=True, exist_ok=True)
    out = {}
    for name, sql in zip(blocks[::2], blocks[1::2]):
        res = pd.read_sql_query(sql, con)
        res.to_csv(RESULTS / f"{name}.csv", index=False)
        out[name] = res
        print(f"  {name:<32} {len(res):>5} rows")
    return out


if __name__ == "__main__":
    DB.unlink(missing_ok=True)
    with sqlite3.connect(DB) as conn:
        load(conn)
        print("Running analysis queries:")
        run_queries(conn)
