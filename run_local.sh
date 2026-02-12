#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

echo "=== Installing dependencies ==="
pip install -q -r requirements.txt

echo "=== Fetching data & generating SRS ratings ==="
python -m scripts.generate_site_data

echo ""
echo "=== Done! Serving site at http://localhost:8000 ==="
echo "Press Ctrl+C to stop."
echo ""
python -m http.server 8000 --directory site
