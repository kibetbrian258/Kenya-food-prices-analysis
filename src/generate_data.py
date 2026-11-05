"""
Generate a synthetic Kenyan food-price dataset in the same schema as the
WFP "Kenya - Food Prices" dataset published on the Humanitarian Data Exchange
(HDX): https://data.humdata.org/dataset/wfp-food-prices-for-kenya

The data are SIMULATED. Price levels, seasonality and shocks are modelled on
well-documented features of Kenyan food markets (long-rains lean season,
the 2021-2023 Horn of Africa drought, higher prices in arid northern
counties, KES depreciation in 2023) but the individual numbers are not real
observations. To run the project on real data, download the HDX CSV and
pass it to src/clean.py instead of this file.

The generator also injects realistic data-quality problems (duplicates,
inconsistent labels, unit mixes, typo outliers, missing months) so that the
cleaning step has real work to do.

Usage:
    python src/generate_data.py            # writes data/raw/wfp_food_prices_ken_synthetic.csv
"""
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42
START, END = "2018-01-01", "2026-09-01"
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "wfp_food_prices_ken_synthetic.csv"

# ---------------------------------------------------------------------------
# Markets: admin1 follows WFP's use of the former provinces, admin2 = county.
# premium = log-price premium vs Nairobi; asal = arid/semi-arid county;
# drought_amp = how strongly the market reacts to the drought shock.
# ---------------------------------------------------------------------------
MARKETS = [
    # market,      admin1,          admin2,       lat,     lon,    premium, asal, drought_amp
    ("Nairobi",    "Nairobi",       "Nairobi",    -1.286,  36.817,  0.00, False, 1.00),
    ("Mombasa",    "Coast",         "Mombasa",    -4.043,  39.668,  0.08, False, 1.05),
    ("Kisumu",     "Nyanza",        "Kisumu",     -0.092,  34.768,  0.02, False, 0.95),
    ("Nakuru",     "Rift Valley",   "Nakuru",     -0.303,  36.080, -0.08, False, 0.85),
    ("Eldoret",    "Rift Valley",   "Uasin Gishu", 0.514,  35.270, -0.15, False, 0.70),
    ("Kakamega",   "Western",       "Kakamega",    0.283,  34.752, -0.03, False, 0.90),
    ("Karatina",   "Central",       "Nyeri",      -0.483,  37.127, -0.05, False, 0.85),
    ("Kitui",      "Eastern",       "Kitui",      -1.367,  38.011,  0.10, True,  1.25),
    ("Garissa",    "North Eastern", "Garissa",    -0.453,  39.646,  0.20, True,  1.40),
    ("Mandera",    "North Eastern", "Mandera",     3.937,  41.856,  0.32, True,  1.55),
    ("Marsabit",   "Eastern",       "Marsabit",    2.335,  37.990,  0.28, True,  1.50),
    ("Lodwar",     "Rift Valley",   "Turkana",     3.119,  35.597,  0.30, True,  1.60),
]

# commodity, category, unit, base Nairobi retail price Jan-2018 (KES),
# drought sensitivity, volatility (sd of AR noise), seasonal profile (12 log offsets)
COMMODITIES = {
    "Maize (white)": dict(category="cereals and tubers", unit="KG", base=40, drought=1.00, vol=0.035,
        season=[-0.02, 0.00, 0.03, 0.06, 0.08, 0.08, 0.04, -0.02, -0.05, -0.07, -0.08, -0.05]),
    "Sorghum": dict(category="cereals and tubers", unit="KG", base=55, drought=0.85, vol=0.035,
        season=[-0.01, 0.01, 0.03, 0.05, 0.06, 0.05, 0.02, -0.01, -0.04, -0.06, -0.06, -0.04]),
    "Beans (rosecoco)": dict(category="pulses and nuts", unit="KG", base=100, drought=0.75, vol=0.03,
        season=[-0.04, -0.01, 0.04, 0.06, 0.03, -0.02, -0.04, -0.02, 0.03, 0.04, -0.03, -0.04]),
    "Green grams": dict(category="pulses and nuts", unit="KG", base=110, drought=0.70, vol=0.03,
        season=[-0.05, -0.03, 0.00, 0.03, 0.05, 0.05, 0.03, 0.01, -0.01, -0.02, -0.03, -0.03]),
    "Potatoes (Irish)": dict(category="cereals and tubers", unit="KG", base=45, drought=0.60, vol=0.07,
        season=[0.02, 0.06, 0.10, 0.12, 0.08, 0.00, -0.10, -0.12, -0.06, 0.00, -0.04, -0.06]),
    "Milk (cow, fresh)": dict(category="milk and dairy", unit="L", base=55, drought=0.65, vol=0.025,
        season=[0.05, 0.07, 0.06, 0.01, -0.04, -0.05, -0.04, -0.02, 0.00, -0.01, -0.02, 0.01]),
}

# Commodity-specific market adjustments (production zones are cheaper)
LOCAL_ADJ = {
    ("Potatoes (Irish)", "Karatina"): -0.22,
    ("Potatoes (Irish)", "Nakuru"): -0.18,
    ("Potatoes (Irish)", "Eldoret"): -0.08,
    ("Green grams", "Kitui"): -0.18,
    ("Milk (cow, fresh)", "Eldoret"): -0.12,
    ("Milk (cow, fresh)", "Nakuru"): -0.10,
    ("Milk (cow, fresh)", "Karatina"): -0.08,
    ("Milk (cow, fresh)", "Mandera"): -0.15,   # pastoral areas: camel/goat milk substitutes
    ("Milk (cow, fresh)", "Marsabit"): -0.10,
    ("Maize (white)", "Kakamega"): -0.04,
}

# Wholesale maize (90 KG bag) reported in the larger urban markets
WHOLESALE_MARKETS = ["Nairobi", "Mombasa", "Kisumu", "Nakuru", "Eldoret"]


def kes_per_usd(dates: pd.DatetimeIndex) -> np.ndarray:
    """Approximate KES/USD path (monthly), interpolated between anchor points."""
    anchors = pd.Series({
        "2018-01-15": 103.0, "2019-01-15": 101.5, "2020-01-15": 101.0, "2020-07-15": 107.0,
        "2021-01-15": 110.0, "2022-01-15": 113.5, "2022-07-15": 118.0, "2023-01-15": 124.0,
        "2023-07-15": 142.0, "2024-01-15": 159.0, "2024-04-15": 132.0, "2024-07-15": 129.5,
        "2025-01-15": 129.3, "2026-09-15": 129.2,
    })
    anchors.index = pd.to_datetime(anchors.index)
    s = anchors.reindex(anchors.index.union(dates)).interpolate("time")
    return s.loc[dates].values


def shock_curve(dates: pd.DatetimeIndex) -> np.ndarray:
    """National supply-shock component in log points (0 = normal year)."""
    anchors = pd.Series({
        "2018-01-15": 0.05, "2018-07-15": -0.05, "2019-01-15": -0.03, "2019-04-15": 0.10,
        "2019-07-15": 0.14, "2019-11-15": 0.00, "2020-04-15": 0.06, "2020-08-15": -0.02,
        "2021-04-15": -0.02, "2021-09-15": 0.02, "2022-01-15": 0.18, "2022-06-15": 0.38,
        "2022-10-15": 0.44, "2023-02-15": 0.46, "2023-05-15": 0.36, "2023-09-15": 0.15,
        "2023-12-15": 0.03, "2024-04-15": -0.06, "2024-08-15": -0.14, "2025-01-15": -0.12,
        "2025-06-15": -0.04, "2025-12-15": 0.00, "2026-04-15": 0.04, "2026-09-15": 0.02,
    })
    anchors.index = pd.to_datetime(anchors.index)
    s = anchors.reindex(anchors.index.union(dates)).interpolate("time")
    return s.loc[dates].values


def simulate() -> pd.DataFrame:
    rng = np.random.default_rng(SEED)
    dates = pd.date_range(START, END, freq="MS") + pd.Timedelta(days=14)
    n = len(dates)
    t_years = (dates - dates[0]).days / 365.25
    trend = 0.055 * t_years                      # ~5.5% a year general inflation
    shock = shock_curve(dates)
    fx = kes_per_usd(dates)
    month_idx = dates.month - 1

    rows = []
    for c_name, c in COMMODITIES.items():
        season = np.array(c["season"])[month_idx]
        # shared commodity-level noise so markets co-move
        common = np.zeros(n)
        for i in range(1, n):
            common[i] = 0.55 * common[i - 1] + rng.normal(0, c["vol"])
        for m, a1, a2, lat, lon, prem, asal, amp in MARKETS:
            local = np.zeros(n)
            for i in range(1, n):
                local[i] = 0.6 * local[i - 1] + rng.normal(0, c["vol"] * (1.3 if asal else 1.0))
            # ASAL markets have stronger seasonal swings (thin markets)
            log_p = (np.log(c["base"]) + prem + LOCAL_ADJ.get((c_name, m), 0.0) + trend
                     + season * (1.25 if asal else 1.0)
                     + shock * c["drought"] * amp + common + local)
            price = np.exp(log_p)
            for i, d in enumerate(dates):
                rows.append((d, a1, a2, m, lat, lon, c["category"], c_name, c["unit"],
                             "actual", "Retail", "KES", round(price[i], 2), fx[i]))
            if c_name == "Maize (white)" and m in WHOLESALE_MARKETS:
                # wholesale per 90 KG bag at ~78-82% of retail per kg
                margin = 0.80 + rng.normal(0, 0.015, n) - 0.02 * (shock > 0.3)
                bag = price * margin * 90
                for i, d in enumerate(dates):
                    rows.append((d, a1, a2, m, lat, lon, c["category"], c_name, "90 KG",
                                 "actual", "Wholesale", "KES", round(bag[i], 0), fx[i]))

    df = pd.DataFrame(rows, columns=["date", "admin1", "admin2", "market", "latitude", "longitude",
                                     "category", "commodity", "unit", "priceflag", "pricetype",
                                     "currency", "price", "_fx"])
    df["usdprice"] = (df["price"] / df["_fx"]).round(4)
    df = df.drop(columns="_fx")
    return inject_quality_issues(df, rng)


def inject_quality_issues(df: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Add the kind of mess found in real market-monitoring data."""
    df = df.copy()
    n = len(df)
    # 1) ~4% of observations missing (markets not visited, more often in ASAL counties)
    asal = df["market"].isin(["Mandera", "Marsabit", "Lodwar", "Garissa"])
    drop_p = np.where(asal, 0.07, 0.025)
    df = df[rng.random(n) > drop_p]
    # Mandera not covered in Apr-Jun 2021 (insecurity)
    gap = (df["market"] == "Mandera") & df["date"].between("2021-04-01", "2021-06-30")
    df = df[~gap]
    # 2) inconsistent commodity labels
    idx = df.sample(frac=0.03, random_state=1).index
    relabel = {"Maize (white)": "maize - white", "Beans (rosecoco)": "Beans (Rosecoco) ",
               "Potatoes (Irish)": "Potatoes (irish)", "Green grams": "Green Grams",
               "Sorghum": "sorghum", "Milk (cow, fresh)": "Milk (cow, fresh) "}
    df.loc[idx, "commodity"] = df.loc[idx, "commodity"].map(relabel)
    # 3) keying errors: decimal slip (x10) on a handful of rows
    idx = df[df["pricetype"] == "Retail"].sample(n=14, random_state=2).index
    df.loc[idx, "price"] = df.loc[idx, "price"] * 10
    # 4) a few prices recorded as zero
    idx = df.sample(n=6, random_state=3).index
    df.loc[idx, ["price", "usdprice"]] = 0
    # 5) exact duplicate rows
    dups = df.sample(n=60, random_state=4)
    df = pd.concat([df, dups])
    # 6) some markets reported with trailing spaces / different case
    idx = df.sample(frac=0.01, random_state=5).index
    df.loc[idx, "market"] = df.loc[idx, "market"].str.upper() + " "
    df = df.sample(frac=1, random_state=6).reset_index(drop=True)
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    return df


if __name__ == "__main__":
    data = simulate()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    data.to_csv(OUT, index=False)
    print(f"Wrote {len(data):,} rows to {OUT.relative_to(ROOT)}")
