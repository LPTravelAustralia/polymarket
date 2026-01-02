# Polymarket Trading Bot - Setup Reference

**Last Updated:** January 2, 2026

## Current Status

### ✅ WORKING
| Component | Status | Notes |
|-----------|--------|-------|
| Frontend (Netlify) | ✅ Live | https://boisterous-basbousa-e11b8a.netlify.app/ |
| Backend (GCloud VM) | ✅ Running | http://136.114.57.247:8000 |
| API Connection | ✅ Working | Frontend → Backend via Netlify proxy |
| Polymarket API | ✅ Working | Fetching live market data |
| Bot Start/Stop | ✅ Working | Via UI or curl |
| Category Filtering | ✅ Working | politics, sports, crypto, finance, entertainment, tech, science, world, elections, ai |
| All 6 Strategies | ✅ Working | momentum, value, arbitrage, combined, ai, news |
| Kelly Criterion Sizing | ✅ Working | Dynamic position sizing |
| Take Profit / Stop Loss | ✅ Working | Auto-exit on profit/loss thresholds |
| Selectable Markets API | ✅ Working | `/api/selectable-markets` endpoint |
| Price Charts | ✅ Working | Historical price data display |
| Activity Log | ✅ Working | Real-time trade notifications |
| Paper Trading | ✅ Working | Simulated trades, no real money |

### ⚠️ NEEDS API KEYS (Falls back to momentum without them)
| Feature | Required Key | How to Add |
|---------|-------------|------------|
| AI Strategy | `OPENAI_API_KEY` | Add to `~/polymarket/.env` on VM |
| News Strategy | `NEWSAPI_KEY` | Add to `~/polymarket/.env` on VM |

### 🔴 NOT WORKING / TODO
| Item | Status | Notes |
|------|--------|-------|
| Live Trading | 🔴 Disabled | Needs wallet keys, currently paper-trading only |
| Manual Market Selection UI | 🔴 Missing | Backend supports it, frontend UI not built |
| PnL Chart | 🟡 Basic | Shows data but needs better visualization |
| Mobile Responsive | 🟡 Partial | Works but could be improved |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│  FRONTEND (Netlify)                                         │
│  URL: https://boisterous-basbousa-e11b8a.netlify.app/       │
│  Source: /frontend                                          │
│  Auto-deploys from: copilot/build-polymarket-trading-bot    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼ (API calls via /api/* proxy)
┌─────────────────────────────────────────────────────────────┐
│  BACKEND (Google Cloud VM)                                  │
│  External IP: 136.114.57.247                                │
│  Port: 8000                                                 │
│  URL: http://136.114.57.247:8000                            │
│  SSH: hello@polymarket-bot (us-central1-a)                  │
│  Source: /backend                                           │
└─────────────────────────────────────────────────────────────┘
```

---

## Trading Strategies

| Strategy | Description | API Key Needed |
|----------|-------------|----------------|
| `momentum` | Price momentum & trend following | No |
| `value` | Mean reversion, buys underpriced markets | No |
| `arbitrage` | Exploits YES+NO mispricing | No |
| `combined` | Weighted combination of all signals | No |
| `ai` | OpenAI-powered analysis | OPENAI_API_KEY |
| `news` | News sentiment analysis | NEWSAPI_KEY |

---

## Bot Configuration Options

All these settings work from the frontend Settings panel:

| Setting | Default | Description |
|---------|---------|-------------|
| `trade_size` | 25.0 | USD per trade |
| `max_markets` | 5 | Max concurrent positions |
| `per_market_cap` | 100.0 | Max exposure per market |
| `global_cap` | 500.0 | Total portfolio cap |
| `drawdown_limit` | 200.0 | Stop trading if losses exceed |
| `poll_interval` | 20 | Seconds between scans |
| `agent` | momentum | Trading strategy to use |
| `categories` | [] | Filter by market category |
| `take_profit` | 0.15 | Exit at +15% gain |
| `stop_loss` | 0.10 | Exit at -10% loss |
| `min_liquidity` | 1000.0 | Min market liquidity |
| `use_kelly_sizing` | false | Enable Kelly Criterion |
| `kelly_fraction` | 0.25 | Fraction of Kelly (0.25 = quarter Kelly) |

---

## Quick Commands

### Deploy Code Updates to VM

```bash
# Run on VM via SSH:
cd ~/polymarket && git pull && find . -name "*.pyc" -delete && sudo systemctl restart polymarket-bot
```

### If Port 8000 is stuck (Address in use error)

```bash
# Run on VM:
sudo fuser -k 8000/tcp && sleep 2 && sudo systemctl start polymarket-bot
```

### Check Backend Status

```bash
sudo systemctl status polymarket-bot
sudo journalctl -u polymarket-bot -n 50
```

### Test API Endpoints

```bash
# Health check
curl http://136.114.57.247:8000/api/status

# Get selectable markets for trading
curl "http://136.114.57.247:8000/api/selectable-markets?category=crypto&limit=10"

# Start bot with specific settings
curl -X POST http://136.114.57.247:8000/api/bot/start \
  -H "Content-Type: application/json" \
  -d '{"agent":"value","categories":["crypto"],"trade_size":25}'

# Stop bot
curl -X POST http://136.114.57.247:8000/api/bot/stop

# View activity log
curl http://136.114.57.247:8000/api/activity
```

---

## GCloud VM Details

- **Project:** polymarket-482905
- **Zone:** us-central1-a
- **Instance:** polymarket-bot
- **Machine Type:** e2-micro (free tier)
- **External IP:** 136.114.57.247
- **SSH User:** hello

### SSH Access

```bash
# Via gcloud CLI
gcloud compute ssh polymarket-bot --zone=us-central1-a --project=polymarket-482905

# Or via browser
https://ssh.cloud.google.com/v2/ssh/projects/polymarket-482905/zones/us-central1-a/instances/polymarket-bot
```

## File Locations on VM

```
~/polymarket/              # Main project directory
~/polymarket/venv/         # Python virtual environment
~/polymarket/.env          # Environment variables (API keys)
~/polymarket/backend/      # Backend source code
```

---

## Next Steps / TODO

### High Priority
1. **Manual Market Selection UI** - Add UI to let user select specific markets to trade
2. **Better PnL visualization** - Improve the equity curve chart
3. **Notifications** - Add alerts when trades execute

### Medium Priority
4. **Volatility/Activity filters** - Add UI controls for `min_volatility`, `min_volume_24h`
5. **More graph usage** - Show more analytics (win rate over time, etc.)
6. **Strategy comparison** - Show which strategy performs best

### Low Priority / Future
7. **Live Trading** - Add wallet integration for real trades
8. **Fee Collection** - Implement performance fee system
9. **Multi-account** - Support multiple users

---

## Environment Variables

### Backend (.env on VM) - Current minimal config:
```env
DRY_RUN=true
LOG_LEVEL=INFO
DEFAULT_TRADE_SIZE=10
```

### For Full Features (add these when ready):
```env
# For AI Strategy
OPENAI_API_KEY=sk-your-key-here

# For News Strategy
NEWSAPI_KEY=your-newsapi-key

# For Live Trading (NOT YET IMPLEMENTED)
POLYGON_WALLET_PRIVATE_KEY=your_key
POLYMARKET_API_KEY=your_key
POLYMARKET_SECRET=your_secret
POLYMARKET_PASSPHRASE=your_passphrase
```

---

## Troubleshooting

### Backend not responding externally
1. Check service: `sudo systemctl status polymarket-bot`
2. Kill stuck process: `sudo fuser -k 8000/tcp`
3. Restart: `sudo systemctl start polymarket-bot`

### Frontend shows no data
1. Check backend is running (curl test above)
2. Hard refresh browser (Ctrl+Shift+R)
3. Check browser console for errors

### Backend crashes repeatedly
1. Check logs: `sudo journalctl -u polymarket-bot -n 100`
2. Check memory: `free -h` (e2-micro has limited RAM)
3. May need to restart VM if OOM

### Old code still running after git pull
```bash
find ~/polymarket -name "*.pyc" -delete
find ~/polymarket -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null
sudo fuser -k 8000/tcp
sudo systemctl start polymarket-bot
```
