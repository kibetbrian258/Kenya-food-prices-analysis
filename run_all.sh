#!/usr/bin/env bash
# Run the full pipeline end to end.
set -euo pipefail
cd "$(dirname "$0")"

python src/generate_data.py
python src/clean.py
python src/load_db.py
jupyter nbconvert --to notebook --execute --inplace notebooks/kenya_food_prices_analysis.ipynb
python src/export_dashboard_data.py
echo "Done. Figures in reports/figures, SQL results in reports/sql_results."
