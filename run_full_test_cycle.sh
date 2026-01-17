#!/bin/bash
# Full test cycle: Open positions → Wait → Close → View stats

set -e

echo "========================================================================"
echo "FULL NEWS TRADING TEST CYCLE"
echo "========================================================================"
echo ""

# Capture session start timestamp
SESSION_START=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
echo "Session start: $SESSION_START"
echo ""

echo "------------------------------------------------------------------------"
echo "STEP 1: Run news monitor (open positions across 5 market categories)"
echo "------------------------------------------------------------------------"
python3 ~/polymarket/frontend_monitor.py
echo ""

echo "------------------------------------------------------------------------"
echo "STEP 2: Wait 3 minutes for price movements..."
echo "------------------------------------------------------------------------"
for i in {1..6}; do
    echo "  [$i/6] Waiting... (30 seconds)"
    sleep 30
done
echo ""

echo "------------------------------------------------------------------------"
echo "STEP 3: Auto-close positions older than 3 minutes"
echo "------------------------------------------------------------------------"
python3 ~/polymarket/quick_close_positions.py
echo ""

echo "------------------------------------------------------------------------"
echo "STEP 4: Query fresh session stats"
echo "------------------------------------------------------------------------"
curl -s "http://localhost:8000/api/stats/since?since=${SESSION_START}" | jq '.'
echo ""

echo "========================================================================"
echo "TEST CYCLE COMPLETE"
echo ""
echo "To run another cycle, execute:"
echo "  bash ~/polymarket/run_full_test_cycle.sh"
echo "========================================================================"
