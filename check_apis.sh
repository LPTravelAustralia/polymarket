#!/bin/bash
# Quick API Connection Test - Run this on the VM
# Usage: bash check_apis.sh

echo "═══════════════════════════════════════════════════════════"
echo "  Polymarket Trading Bot - API Connection Quick Test"
echo "═══════════════════════════════════════════════════════════"
echo ""

# Load environment
if [ -f ~/.env ]; then
    export $(cat ~/.env | grep -v '^#' | xargs)
    echo "✓ Loaded .env configuration"
else
    echo "✗ No .env file found at ~/.env"
    exit 1
fi

echo ""
echo "───────────────────────────────────────────────────────────"
echo "Checking API Key Configuration"
echo "───────────────────────────────────────────────────────────"
echo ""

# Check Anthropic
if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "✗ ANTHROPIC_API_KEY: NOT SET"
else
    KEY_DISPLAY="${ANTHROPIC_API_KEY:0:10}...${ANTHROPIC_API_KEY: -10}"
    echo "✓ ANTHROPIC_API_KEY: $KEY_DISPLAY"
fi

# Check OpenAI
if [ -z "$OPENAI_API_KEY" ]; then
    echo "⚠ OPENAI_API_KEY: NOT SET (optional fallback)"
else
    KEY_DISPLAY="${OPENAI_API_KEY:0:10}...${OPENAI_API_KEY: -10}"
    echo "✓ OPENAI_API_KEY: $KEY_DISPLAY"
fi

# Check NewsAPI
if [ -z "$NEWSAPI_KEY" ]; then
    echo "✗ NEWSAPI_KEY: NOT SET"
else
    KEY_DISPLAY="${NEWSAPI_KEY:0:10}...${NEWSAPI_KEY: -10}"
    echo "✓ NEWSAPI_KEY: $KEY_DISPLAY"
fi

# Check Tavily
if [ -z "$TAVILY_API_KEY" ]; then
    echo "✗ TAVILY_API_KEY: NOT SET"
else
    KEY_DISPLAY="${TAVILY_API_KEY:0:10}...${TAVILY_API_KEY: -10}"
    echo "✓ TAVILY_API_KEY: $KEY_DISPLAY"
fi

echo ""
echo "───────────────────────────────────────────────────────────"
echo "Testing API Connectivity"
echo "───────────────────────────────────────────────────────────"
echo ""

# Test Gamma API
echo -n "Testing Gamma API (Polymarket)... "
GAMMA_TEST=$(curl -s -m 5 "https://gamma-api.polymarket.com/markets?limit=1" | jq -r 'length' 2>/dev/null || echo "error")
if [ "$GAMMA_TEST" != "error" ]; then
    echo "✓ PASSED (retrieved 1 market)"
else
    echo "✗ FAILED"
fi

# Test NewsAPI
if [ ! -z "$NEWSAPI_KEY" ] && [ "$NEWSAPI_KEY" != "your_newsapi_key_here" ]; then
    echo -n "Testing NewsAPI... "
    NEWS_TEST=$(curl -s -m 5 "https://newsapi.org/v2/everything?q=trump&apiKey=$NEWSAPI_KEY&pageSize=1" | jq -r '.articles | length' 2>/dev/null || echo "error")
    if [ "$NEWS_TEST" != "error" ]; then
        echo "✓ PASSED (retrieved $NEWS_TEST articles)"
    else
        echo "✗ FAILED"
    fi
else
    echo "⚠ NewsAPI: Skipped (no valid API key)"
fi

# Test Tavily
if [ ! -z "$TAVILY_API_KEY" ] && [ "$TAVILY_API_KEY" != "your_tavily_api_key_here" ]; then
    echo -n "Testing Tavily API... "
    TAVILY_TEST=$(curl -s -m 5 -X POST "https://api.tavily.com/search" \
        -H "Content-Type: application/json" \
        -d "{\"api_key\": \"$TAVILY_API_KEY\", \"query\": \"test\", \"num_results\": 1}" \
        | jq -r '.results | length' 2>/dev/null || echo "error")
    if [ "$TAVILY_TEST" != "error" ]; then
        echo "✓ PASSED (retrieved $TAVILY_TEST results)"
    else
        echo "✗ FAILED"
    fi
else
    echo "⚠ Tavily API: Skipped (no valid API key)"
fi

echo ""
echo "───────────────────────────────────────────────────────────"
echo "Testing Backend Service"
echo "───────────────────────────────────────────────────────────"
echo ""

# Test backend status
echo -n "Testing Backend API (/api/status)... "
STATUS_TEST=$(curl -s -m 5 "http://localhost:8000/api/status" | jq -r '.running' 2>/dev/null || echo "error")
if [ "$STATUS_TEST" != "error" ]; then
    echo "✓ PASSED (service responding)"
else
    echo "✗ FAILED (backend not responding)"
fi

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  Test Complete"
echo "═══════════════════════════════════════════════════════════"
