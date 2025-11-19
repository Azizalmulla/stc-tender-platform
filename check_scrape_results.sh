#!/bin/bash
# Check scrape results

echo "=========================================="
echo "SCRAPE RESULTS"
echo "=========================================="
echo ""

echo "📊 Tender Statistics:"
curl -s https://stc-tender-platform.onrender.com/api/tenders/stats/summary | python3 -m json.tool
echo ""

echo "=========================================="
echo "📅 Meeting Statistics:"
curl -s https://stc-tender-platform.onrender.com/api/meetings/ | python3 -c "import sys, json; data = json.load(sys.stdin); print(f'Total: {data[\"total\"]}'); print(f'Upcoming: {data[\"upcoming\"]}'); print(f'Past: {data[\"past\"]}')"
echo ""

echo "=========================================="
echo "🔔 Notification Statistics:"
curl -s https://stc-tender-platform.onrender.com/api/notifications/ | python3 -c "import sys, json; data = json.load(sys.stdin); print(f'Postponed: {data[\"postponed\"]}'); print(f'New (7 days): {data[\"new\"]}'); print(f'Deadlines (14 days): {data[\"deadlines\"]}')"
echo ""

echo "=========================================="
