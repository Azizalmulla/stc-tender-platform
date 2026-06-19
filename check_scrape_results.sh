#!/bin/bash
# Check scrape results.
# Defaults to the local VPS API; override with: BASE_URL=https://api.example.com ./check_scrape_results.sh
BASE_URL="${BASE_URL:-http://localhost:8000}"

echo "=========================================="
echo "SCRAPE RESULTS  ($BASE_URL)"
echo "=========================================="
echo ""

echo "📊 Tender Statistics:"
curl -s "$BASE_URL/api/tenders/stats/summary" | python3 -m json.tool
echo ""

echo "=========================================="
echo "📅 Meeting Statistics:"
curl -s "$BASE_URL/api/meetings/" | python3 -c "import sys, json; data = json.load(sys.stdin); print(f'Total: {data[\"total\"]}'); print(f'Upcoming: {data[\"upcoming\"]}'); print(f'Past: {data[\"past\"]}')"
echo ""

echo "=========================================="
echo "🔔 Notification Statistics:"
curl -s "$BASE_URL/api/notifications/" | python3 -c "import sys, json; data = json.load(sys.stdin); print(f'Postponed: {data[\"postponed\"]}'); print(f'New (7 days): {data[\"new\"]}'); print(f'Deadlines (14 days): {data[\"deadlines\"]}')"
echo ""

echo "=========================================="
