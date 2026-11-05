"""
Export the compact JSON files the interactive dashboard reads.

  reports/dashboard_data/retail_prices.json   monthly retail price per market x commodity (from SQLite)
  reports/dashboard_data/seasonal_index.json  seasonal index (sql q04)
  reports/dashboard_data/forecast_maize_nairobi.json  12-month SARIMA forecast (from the notebook)

Usage:
    python src/export_dashboard_data.py
"""
import json
import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "dashboard_data"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(ROOT / "data" / "kenya_food_prices.db") as con:
        prices = pd.read_sql_query(
            """SELECT month, market, zone, commodity, unit, ROUND(price_kes, 2) AS price
               FROM v_price WHERE price_type = 'Retail' ORDER BY commodity, market, month""", con)
    season = pd.read_csv(ROOT / "reports" / "sql_results" / "q04_seasonal_index.csv")
    forecast = pd.read_csv(ROOT / "reports" / "forecast_maize_nairobi.csv")

    for name, df in [("retail_prices", prices), ("seasonal_index", season), ("forecast_maize_nairobi", forecast)]:
        path = OUT / f"{name}.json"
        path.write_text(json.dumps(df.to_dict(orient="records"), separators=(",", ":")))
        print(f"{path.relative_to(ROOT)}: {len(df):,} rows, {path.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
