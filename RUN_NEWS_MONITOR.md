# Running the News Monitor - Instructions

## System Architecture

```
Codespace (This Repository)              GCloud VM (Production)
├── scripts/run_news_monitor.py           ├── Backend (http://34.29.163.176:8000)
├── src/agents/news_monitor_agent.py      │   └── Has API keys configured
└── (No API keys needed here)             │       ✅ NEWSAPI_KEY
                                          │       ✅ ANTHROPIC_API_KEY
                                          │
                                          └── News Monitor runs here
                                              └── Calls backend for analysis
```

## Quick Start

### 1. Start the Backend on GCloud VM

**IMPORTANT:** Backend must be started from the `~/polymarket` root directory (not `~/polymarket/backend`) to properly load the `.env` file.

```bash
cd ~/polymarket

# Load environment variables from .env file
set -a
source .env
set +a

# Start backend from root directory
nohup python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 > backend/backend.log 2>&1 &

# Verify it's running and has API keys
curl http://localhost:8000/api/health
# Should show: "anthropic_key":true, "newsapi_key":true
```

The backend will be accessible at:
```
http://34.29.163.176:8000
```

It loads API keys from `~/polymarket/.env`:
- ✅ NewsAPI key (for fetching news)
- ✅ Anthropic key (Claude AI for analysis)
- ✅ Polymarket API credentials

### 2. Run the News Monitor on the GCloud VM

SSH into the server:
```bash
ssh hello@polymarket-bot
cd polymarket
```

Start the news monitor (will run for 1 iteration and exit):
```bash
python3 scripts/run_news_monitor.py --once --dry-run
```

Or run continuously (checks every 5 minutes):
```bash
python3 scripts/run_news_monitor.py --dry-run
```

### 3. Monitor from Codespace

While the news monitor is running on the VM, you can watch it from here:

```bash
# Watch backend for trading activity
python3 watch_trading.py
```

This will:
- Poll backend every 5 seconds
- Show bot status (RUNNING/STOPPED)
- Display trades executed
- Show PnL changes in real-time
- List recent activity

## What Happens

### News Monitor Workflow
1. **Fetch News** → Calls backend `/api/news` endpoint
   - Backend uses NewsAPI key (configured there)
   - Returns relevant news articles

2. **Match Markets** → Matches articles to active markets
   - Extracts keywords from market questions
   - Finds articles matching those keywords

3. **AI Analysis** → Calls backend `/api/news/analyze` endpoint
   - Backend uses Claude AI (configured there)
   - Analyzes news impact on market
   - Returns impact score, confidence, direction

4. **Generate Signals** → Creates trading signals for high-score articles
   - Impact score ≥ 0.55
   - Confidence ≥ 0.50

5. **Execute Trades** → Places trades on Polymarket
   - Paper trading mode (dry run, no real money)
   - Logs to backend activity feed

### Monitoring Workflow
1. **Connect to Backend** → Calls `http://34.29.163.176:8000/api/`
2. **Poll Status** → Every 5 seconds gets:
   - Bot status (running/stopped)
   - Trades today count
   - Total PnL
   - Active positions
   - Recent activity

3. **Detect Changes** → Alerts when:
   - New trades are executed
   - PnL changes
   - Bot starts/stops

## Environment Variables

The news monitor reads from:
- `POLYMARKET_API_KEY` - Polymarket credentials
- `POLYMARKET_SECRET` - Polymarket credentials
- `POLYMARKET_PASSPHRASE` - Polymarket credentials

These are read from `~/.env` on the GCloud VM.

**Note**: It does NOT need NewsAPI or Anthropic keys locally - it calls the backend which has them.

## Example Run

### Terminal 1 (GCloud VM) - Start News Monitor
```bash
$ ssh hello@polymarket-bot
$ cd polymarket
$ python3 scripts/run_news_monitor.py --once --dry-run

2026-01-17 12:00:00 | INFO | Checking for breaking news...
2026-01-17 12:00:05 | INFO | Found 79 articles
2026-01-17 12:00:10 | INFO | ✓ MATCH: "Tesla announces new factory" → Tesla stock market
2026-01-17 12:00:15 | INFO | Analyzing news impact with backend API...
2026-01-17 12:00:20 | INFO | Generated signal: IMPACT=0.78, CONF=0.82, DIR=YES
2026-01-17 12:00:25 | INFO | Executing trade...
2026-01-17 12:00:30 | INFO | Trade executed: Buy 50 YES @ $0.62 on Tesla market
```

### Terminal 2 (Codespace) - Monitor Backend
```bash
$ python3 watch_trading.py

🚀 FRONTEND LIVE MONITORING STARTED
==========================================================================================
[  0s | CHECK # 1] 🟢 RUNNING   | Trades: 0  |  | Positions: 54
[  5s | CHECK # 2] 🟢 RUNNING   | Trades: 1  | 🆕 NEW TRADE EXECUTED! | 💰 PnL: $0.00 → $12.50
[ 10s | CHECK # 3] 🟢 RUNNING   | Trades: 1  |  | Positions: 55
[ 15s | CHECK # 4] 🟢 RUNNING   | Trades: 2  | 🆕 NEW TRADE EXECUTED! | 💰 PnL: $12.50 → $28.75
[ 20s | CHECK # 5] 🟢 RUNNING   | Trades: 2  |  | Positions: 56
```

**You would see actual trades, PnL changes, and activity happening in real-time!**

## Troubleshooting

### "Backend not responding"
- Check GCloud VM is running: `gcloud compute instances list`
- Check backend process: `ssh hello@polymarket-bot` then `ps aux | grep main.py`
- Check firewall allows port 8000

### "NewsAPI not finding articles"
- Check NewsAPI key is set on VM: `cat ~/.env | grep NEWSAPI`
- Check backend `/api/news` endpoint: `curl http://34.29.163.176:8000/api/news?query=test`

### "No trades being generated"
- Check impact/confidence thresholds: `grep news_min_ src/core/config.py`
- Current: impact ≥ 0.55, confidence ≥ 0.50
- Increase trading if too few matches

## Live Frontend

You can also watch live on the frontend:
```
https://boisterous-basbousa-e11b8a.netlify.app/
```

Refresh to see:
- Real-time trades executing
- PnL updates
- Activity log
- Position changes

---

**Remember**: Backend has all the API keys. News monitor just orchestrates the workflow and calls backend endpoints for external data.
