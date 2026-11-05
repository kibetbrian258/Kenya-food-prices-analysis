-- =====================================================================
-- Kenya food prices: SQL analysis (SQLite 3.25+ for window functions)
-- Each query is preceded by "-- name: <query_name>" so src/load_db.py
-- can run them and save results to reports/sql_results/<query_name>.csv
-- =====================================================================


-- name: q01_data_coverage
-- Q: How complete is the monitoring panel for each market?
SELECT m.market,
       m.county,
       m.zone,
       COUNT(*)                                                     AS observations,
       COUNT(DISTINCT f.month)                                      AS months_reported,
       (SELECT COUNT(DISTINCT month) FROM fact_price)               AS months_in_period,
       ROUND(100.0 * COUNT(*) /
             ((SELECT COUNT(DISTINCT month) FROM fact_price) *
              COUNT(DISTINCT f.commodity_id || f.price_type)), 1)   AS coverage_pct
FROM fact_price f
JOIN dim_market m USING (market_id)
GROUP BY m.market, m.county, m.zone
ORDER BY coverage_pct;


-- name: q02_national_monthly_index
-- Q: How have national average retail prices moved, and what is the
--    year-on-year change each month? (LAG over a monthly series)
WITH national AS (
    SELECT commodity, month, AVG(price_kes) AS avg_price_kes
    FROM v_price
    WHERE price_type = 'Retail'
    GROUP BY commodity, month
)
SELECT commodity,
       month,
       ROUND(avg_price_kes, 2) AS avg_price_kes,
       ROUND(100.0 * (avg_price_kes / LAG(avg_price_kes, 12) OVER w - 1), 1) AS yoy_pct,
       ROUND(AVG(avg_price_kes) OVER (PARTITION BY commodity ORDER BY month
                                      ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 2) AS rolling_3m_kes
FROM national
WINDOW w AS (PARTITION BY commodity ORDER BY month)
ORDER BY commodity, month;


-- name: q03_drought_impact_maize
-- Q: How much did maize prices rise during the 2021-23 drought, by market?
--    Baseline = average 2019-2020; peak = highest month Oct 2021 - Dec 2023.
WITH base AS (
    SELECT market, zone, AVG(price_kes) AS baseline
    FROM v_price
    WHERE commodity = 'Maize (white)' AND price_type = 'Retail' AND year IN (2019, 2020)
    GROUP BY market, zone
),
peak AS (
    SELECT market, MAX(price_kes) AS peak_price
    FROM v_price
    WHERE commodity = 'Maize (white)' AND price_type = 'Retail'
      AND month BETWEEN '2021-10-01' AND '2023-12-01'
    GROUP BY market
),
peak_month AS (
    SELECT v.market, MIN(v.month) AS peak_month
    FROM v_price v JOIN peak p ON p.market = v.market AND v.price_kes = p.peak_price
    WHERE v.commodity = 'Maize (white)' AND v.price_type = 'Retail'
    GROUP BY v.market
)
SELECT b.market,
       b.zone,
       ROUND(b.baseline, 2)                          AS baseline_2019_20_kes,
       ROUND(p.peak_price, 2)                        AS drought_peak_kes,
       pm.peak_month,
       ROUND(100.0 * (p.peak_price / b.baseline - 1), 1) AS increase_pct,
       RANK() OVER (ORDER BY p.peak_price / b.baseline DESC) AS rank_hardest_hit
FROM base b
JOIN peak p USING (market)
JOIN peak_month pm USING (market)
ORDER BY rank_hardest_hit;


-- name: q04_seasonal_index
-- Q: In which months are prices seasonally high or low?
--    Seasonal index = price / that market-commodity's average for the same
--    year, averaged across markets and years (100 = annual average).
WITH ratio AS (
    SELECT commodity, month_num,
           price_kes / AVG(price_kes) OVER (PARTITION BY market, commodity, year) AS r
    FROM v_price
    WHERE price_type = 'Retail' AND year BETWEEN 2018 AND 2025   -- full calendar years only
)
SELECT commodity,
       month_num,
       ROUND(100 * AVG(r), 1) AS seasonal_index
FROM ratio
GROUP BY commodity, month_num
ORDER BY commodity, month_num;


-- name: q05_asal_premium
-- Q: How much more do households in arid/semi-arid (ASAL) markets pay?
WITH yearly AS (
    SELECT commodity, year, zone, AVG(price_kes) AS avg_price
    FROM v_price
    WHERE price_type = 'Retail'
    GROUP BY commodity, year, zone
)
SELECT a.commodity,
       a.year,
       ROUND(h.avg_price, 2) AS high_potential_kes,
       ROUND(a.avg_price, 2) AS asal_kes,
       ROUND(100.0 * (a.avg_price / h.avg_price - 1), 1) AS asal_premium_pct
FROM yearly a
JOIN yearly h ON h.commodity = a.commodity AND h.year = a.year AND h.zone = 'High-potential'
WHERE a.zone = 'ASAL'
ORDER BY a.commodity, a.year;


-- name: q06_volatility
-- Q: Which commodities have the most volatile prices?
--    Volatility = standard deviation of month-on-month log changes (%).
WITH changes AS (
    SELECT commodity, market,
           100 * (ln(price_kes) - ln(LAG(price_kes) OVER (PARTITION BY market, commodity ORDER BY month))) AS mom
    FROM v_price
    WHERE price_type = 'Retail'
)
SELECT commodity,
       COUNT(mom)                                          AS n_changes,
       ROUND(AVG(mom), 2)                                  AS mean_mom_pct,
       ROUND(sqrt(AVG(mom * mom) - AVG(mom) * AVG(mom)), 2) AS volatility_pct,
       ROUND(MAX(mom), 1)                                  AS largest_rise_pct,
       ROUND(MIN(mom), 1)                                  AS largest_fall_pct
FROM changes
WHERE mom IS NOT NULL
GROUP BY commodity
ORDER BY volatility_pct DESC;


-- name: q07_maize_retail_wholesale_margin
-- Q: What share of the retail maize price is the wholesale price, and how
--    did the retail mark-up behave during the drought?
SELECT r.market,
       r.year,
       ROUND(AVG(r.price_kes), 2)                          AS retail_kes_per_kg,
       ROUND(AVG(w.price_kes), 2)                          AS wholesale_kes_per_kg,
       ROUND(100.0 * (AVG(r.price_kes) / AVG(w.price_kes) - 1), 1) AS retail_markup_pct
FROM v_price r
JOIN v_price w
  ON w.market = r.market AND w.month = r.month AND w.commodity = r.commodity
 AND w.price_type = 'Wholesale'
WHERE r.commodity = 'Maize (white)' AND r.price_type = 'Retail'
GROUP BY r.market, r.year
ORDER BY r.market, r.year;


-- name: q08_latest_snapshot
-- Q: Where are prices now, and how do they compare with a year ago?
WITH latest AS (SELECT MAX(month) AS m FROM fact_price)
SELECT cur.commodity,
       cur.market,
       cur.zone,
       cur.price_kes                                        AS price_now_kes,
       prev.price_kes                                       AS price_year_ago_kes,
       ROUND(100.0 * (cur.price_kes / prev.price_kes - 1), 1) AS yoy_pct,
       DENSE_RANK() OVER (PARTITION BY cur.commodity ORDER BY cur.price_kes) AS cheapest_rank
FROM v_price cur
CROSS JOIN latest
LEFT JOIN v_price prev
       ON prev.market = cur.market AND prev.commodity = cur.commodity
      AND prev.price_type = cur.price_type
      AND prev.month = date(latest.m, '-12 months')
WHERE cur.price_type = 'Retail' AND cur.month = latest.m
ORDER BY cur.commodity, cheapest_rank;


-- name: q09_price_in_usd_vs_kes
-- Q: How much of the change in prices is a currency effect?
--    Annual national average maize price in KES and USD, indexed to 2019 = 100.
WITH annual AS (
    SELECT year, AVG(price_kes) AS kes, AVG(price_usd) AS usd
    FROM v_price
    WHERE commodity = 'Maize (white)' AND price_type = 'Retail'
    GROUP BY year
),
fx AS (SELECT CAST(strftime('%Y', month) AS INTEGER) AS year, AVG(kes_per_usd) AS kes_per_usd
       FROM dim_fx GROUP BY 1)
SELECT a.year,
       ROUND(a.kes, 2)                                         AS maize_kes,
       ROUND(a.usd, 3)                                         AS maize_usd,
       ROUND(fx.kes_per_usd, 1)                                AS kes_per_usd,
       ROUND(100 * a.kes / (SELECT kes FROM annual WHERE year = 2019), 1) AS kes_index_2019,
       ROUND(100 * a.usd / (SELECT usd FROM annual WHERE year = 2019), 1) AS usd_index_2019
FROM annual a JOIN fx USING (year)
ORDER BY a.year;


-- name: q10_market_integration
-- Q: How closely do regional maize prices follow Nairobi?
--    Pearson correlation of monthly prices with Nairobi, computed in SQL.
WITH nbo AS (
    SELECT month, price_kes AS p_nbo
    FROM v_price
    WHERE market = 'Nairobi' AND commodity = 'Maize (white)' AND price_type = 'Retail'
),
pairs AS (
    SELECT v.market, v.zone, v.price_kes AS x, n.p_nbo AS y
    FROM v_price v JOIN nbo n USING (month)
    WHERE v.commodity = 'Maize (white)' AND v.price_type = 'Retail' AND v.market <> 'Nairobi'
)
SELECT market,
       zone,
       COUNT(*) AS n_months,
       ROUND((AVG(x * y) - AVG(x) * AVG(y)) /
             (sqrt(AVG(x * x) - AVG(x) * AVG(x)) * sqrt(AVG(y * y) - AVG(y) * AVG(y))), 3) AS corr_with_nairobi,
       ROUND(100.0 * (AVG(x) / AVG(y) - 1), 1) AS avg_gap_vs_nairobi_pct
FROM pairs
GROUP BY market, zone
ORDER BY corr_with_nairobi DESC;
