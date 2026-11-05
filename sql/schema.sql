-- Star schema for Kenyan market price monitoring (SQLite)
DROP TABLE IF EXISTS fact_price;
DROP TABLE IF EXISTS dim_market;
DROP TABLE IF EXISTS dim_commodity;
DROP TABLE IF EXISTS dim_fx;

CREATE TABLE dim_market (
    market_id   INTEGER PRIMARY KEY,
    market      TEXT NOT NULL UNIQUE,
    county      TEXT NOT NULL,      -- admin2
    region      TEXT NOT NULL,      -- admin1 (former province)
    zone        TEXT NOT NULL CHECK (zone IN ('ASAL', 'High-potential')),
    latitude    REAL,
    longitude   REAL
);

CREATE TABLE dim_commodity (
    commodity_id INTEGER PRIMARY KEY,
    commodity    TEXT NOT NULL UNIQUE,
    category     TEXT NOT NULL,
    unit         TEXT NOT NULL      -- price unit after cleaning (KG or L)
);

CREATE TABLE dim_fx (
    month       DATE PRIMARY KEY,
    kes_per_usd REAL NOT NULL
);

CREATE TABLE fact_price (
    month        DATE    NOT NULL,
    market_id    INTEGER NOT NULL REFERENCES dim_market(market_id),
    commodity_id INTEGER NOT NULL REFERENCES dim_commodity(commodity_id),
    price_type   TEXT    NOT NULL CHECK (price_type IN ('Retail', 'Wholesale')),
    price_kes    REAL    NOT NULL CHECK (price_kes > 0),
    price_usd    REAL,
    PRIMARY KEY (month, market_id, commodity_id, price_type)
);

CREATE INDEX ix_price_commodity_month ON fact_price (commodity_id, month);
CREATE INDEX ix_price_market ON fact_price (market_id);

-- Convenience view used by most analysis queries
DROP VIEW IF EXISTS v_price;
CREATE VIEW v_price AS
SELECT f.month,
       CAST(strftime('%Y', f.month) AS INTEGER) AS year,
       CAST(strftime('%m', f.month) AS INTEGER) AS month_num,
       m.market, m.county, m.region, m.zone,
       c.commodity, c.category, c.unit,
       f.price_type, f.price_kes, f.price_usd
FROM fact_price f
JOIN dim_market    m USING (market_id)
JOIN dim_commodity c USING (commodity_id);
