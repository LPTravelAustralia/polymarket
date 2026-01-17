#!/bin/bash
# Clean test cycle: Close all positions → Run monitor → Wait → Close → Stats

set -e

echo "========================================================================"
echo "CLEAN NEWS TRADING TEST CYCLE"
echo "========================================================================"
echo ""

# Optional: Close all positions first for clean slate
if [ "$1" == "--fresh" ] || [ "$1" == "-f" ]; then
    echo "------------------------------------------------------------------------"
    echo "STEP 0: Close all open positions (fresh start)"
    echo "------------------------------------------------------------------------"
    python3 ~/polymarket/close_all_positions.py
    echo ""
fi

# Capture session start timestamp
SESSION_START=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
echo "Session start: $SESSION_START"
echo ""

echo "------------------------------------------------------------------------"
echo "STEP 1: Run news monitor (market-specific article searches)"
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
echo "Usage:"
echo "  bash ~/polymarket/run_clean_test_cycle.sh          # Run as-is"
echo "  bash ~/polymarket/run_clean_test_cycle.sh --fresh  # Close all first"
echo "========================================================================"
