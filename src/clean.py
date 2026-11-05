"""
Clean the raw WFP-format price file.

Works on both the synthetic file and the real HDX download
(wfp_food_prices_ken.csv). The real file has a second header row of HXL tags
(#date, #adm1+name, ...) which is dropped automatically.

Steps
  1. Drop HXL tag row, parse types
  2. Standardise text labels (market, commodity) to canonical names
  3. Remove exact duplicates and duplicate market-commodity-month records
  4. Remove zero / negative prices
  5. Convert bulk units (e.g. 90 KG bag) to a per-KG price
  6. Detect keying errors (decimal slips) with a robust z-score against the
     market-commodity rolling median; repair x10 slips, drop the rest
  7. Write data/processed/prices_clean.csv and a cleaning log

Usage:
    python src/clean.py [path/to/raw.csv]
"""
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "wfp_food_prices_ken_synthetic.csv"
OUT = ROOT / "data" / "processed" / "prices_clean.csv"
LOG = ROOT / "reports" / "cleaning_log.md"

CANONICAL_COMMODITIES = {
    "maize (white)": "Maize (white)", "maize - white": "Maize (white)", "maize white": "Maize (white)",
    "sorghum": "Sorghum",
    "beans (rosecoco)": "Beans (rosecoco)",
    "green grams": "Green grams",
    "potatoes (irish)": "Potatoes (Irish)",
    "milk (cow, fresh)": "Milk (cow, fresh)",
}


def normalise(s: str) -> str:
    return re.sub(r"\s+", " ", str(s)).strip().lower()


def clean(raw_path: Path) -> tuple[pd.DataFrame, list[str]]:
    log = []
    df = pd.read_csv(raw_path)
    log.append(f"Loaded `{raw_path.name}`: {len(df):,} rows, {df.shape[1]} columns")

    # 1. HXL row (real HDX file) + types
    if str(df.iloc[0]["date"]).startswith("#"):
        df = df.iloc[1:]
        log.append("Dropped HXL tag row")
    df["date"] = pd.to_datetime(df["date"])
    for col in ["price", "usdprice", "latitude", "longitude"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # 2. labels
    before = df["commodity"].nunique(), df["market"].nunique()
    df["market"] = df["market"].map(lambda s: normalise(s).title())
    key = df["commodity"].map(normalise)
    df["commodity"] = key.map(CANONICAL_COMMODITIES).fillna(df["commodity"].str.strip())
    log.append(f"Standardised labels: commodities {before[0]} -> {df['commodity'].nunique()}, "
               f"markets {before[1]} -> {df['market'].nunique()}")

    # 3. duplicates
    n0 = len(df)
    df = df.drop_duplicates()
    log.append(f"Removed {n0 - len(df):,} exact duplicate rows")
    keys = ["date", "market", "commodity", "pricetype", "unit"]
    n0 = len(df)
    df = df.groupby(keys, as_index=False).agg({c: "first" for c in df.columns if c not in keys + ["price", "usdprice"]}
                                              | {"price": "median", "usdprice": "median"})
    log.append(f"Collapsed {n0 - len(df):,} conflicting duplicates (median kept)")

    # 4. invalid prices
    n0 = len(df)
    df = df[df["price"] > 0]
    log.append(f"Removed {n0 - len(df):,} rows with zero/negative/missing price")

    # 5. units -> per KG / per L
    bulk = df["unit"].str.extract(r"^(\d+(?:\.\d+)?)\s*KG$", expand=False).astype(float)
    mask = bulk.notna() & (bulk != 1)
    df.loc[mask, "price"] = df.loc[mask, "price"] / bulk[mask]
    df.loc[mask, "usdprice"] = df.loc[mask, "usdprice"] / bulk[mask]
    df.loc[mask, "unit"] = "KG"
    log.append(f"Converted {mask.sum():,} bulk-unit prices (e.g. 90 KG bag) to per-KG")

    # 6. outliers: robust z on log price vs centred rolling median per series
    df = df.sort_values(keys)
    series = ["market", "commodity", "pricetype"]
    lp = np.log(df["price"])
    med = lp.groupby([df[c] for c in series]).transform(
        lambda s: s.rolling(7, center=True, min_periods=3).median())
    resid = lp - med
    mad = resid.groupby([df[c] for c in series]).transform(lambda s: (s - s.median()).abs().median())
    z = resid / (1.4826 * mad.replace(0, np.nan))
    suspect = (z.abs() > 6) & (resid.abs() > np.log(2.5))   # far from neighbours AND >2.5x off
    slip = suspect & (resid.sub(np.log(10)).abs() < 0.25)          # ~10x too high
    df.loc[slip, "price"] /= 10
    df.loc[slip, "usdprice"] /= 10
    drop = suspect & ~slip
    df = df[~drop]
    log.append(f"Outlier check (|robust z| > 6 and >2.5x off rolling median): repaired {slip.sum()} decimal slips (/10), dropped {drop.sum()} others")

    # tidy columns
    df["price"] = df["price"].round(2)
    df["usdprice"] = df["usdprice"].round(4)
    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.month
    df["date"] = df["date"].dt.to_period("M").dt.to_timestamp()
    df = df.sort_values(["commodity", "market", "pricetype", "date"]).reset_index(drop=True)

    # coverage
    expected = (df.groupby(["market", "commodity", "pricetype"]).ngroups * df["date"].nunique())
    log.append(f"Final: {len(df):,} rows; {df['market'].nunique()} markets, {df['commodity'].nunique()} commodities, "
               f"{df['date'].min():%b %Y} - {df['date'].max():%b %Y}; panel coverage {len(df) / expected:.1%}")
    return df, log


if __name__ == "__main__":
    raw = Path(sys.argv[1]) if len(sys.argv) > 1 else RAW
    clean_df, steps = clean(raw)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    clean_df.to_csv(OUT, index=False)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    LOG.write_text("# Cleaning log\n\n" + "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1)) + "\n")
    print("\n".join(steps))
