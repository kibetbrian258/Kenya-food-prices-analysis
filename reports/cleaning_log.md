# Cleaning log

1. Loaded `wfp_food_prices_ken_synthetic.csv`: 7,811 rows, 14 columns
2. Standardised labels: commodities 12 -> 6, markets 24 -> 12
3. Removed 60 exact duplicate rows
4. Collapsed 0 conflicting duplicates (median kept)
5. Removed 6 rows with zero/negative/missing price
6. Converted 511 bulk-unit prices (e.g. 90 KG bag) to per-KG
7. Outlier check (|robust z| > 6 and >2.5x off rolling median): repaired 14 decimal slips (/10), dropped 0 others
8. Final: 7,745 rows; 12 markets, 6 commodities, Jan 2018 - Sep 2026; panel coverage 95.8%
