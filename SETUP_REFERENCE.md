# Polymarket Trading Bot - Setup Reference

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

## Quick Commands

### If Backend Stops (Run on GCloud VM via SSH)

```bash
# Check status
sudo systemctl status polymarket-bot

# Restart if needed
sudo systemctl restart polymarket-bot

# View logs
sudo journalctl -u polymarket-bot -f
```

### If Backend Needs Code Update (Run on GCloud VM)

```bash
cd ~/polymarket
git pull origin copilot/build-polymarket-trading-bot
source ~/polymarket/venv/bin/activate
pip install -r requirements.txt
pip install -r backend/requirements.txt
sudo systemctl restart polymarket-bot
```

### If Frontend Needs Redeploy (Run locally in VS Code)

```bash
cd /workspaces/polymarket
git commit --allow-empty -m "Trigger Netlify redeploy"
git push origin copilot/build-polymarket-trading-bot
```

### Test Backend is Running

```bash
# From anywhere
curl http://136.114.57.247:8000/

# Expected response:
# {"status":"ok","service":"Polymarket Trading Bot API","version":"1.0.0",...}
```

### Test API Endpoints

```bash
curl http://136.114.57.247:8000/api/markets | head -100
curl http://136.114.57.247:8000/api/events | head -100
curl http://136.114.57.247:8000/api/bot/status
```

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

## Netlify Configuration

- **Site:** boisterous-basbousa-e11b8a
- **Build Command:** `npm run build`
- **Publish Directory:** `.next`
- **Base Directory:** `frontend`
- **API Proxy:** `/api/*` → `http://136.114.57.247:8000/api/:splat`

## Environment Variables

### Backend (.env on VM) - Current minimal config:
```env
DRY_RUN=true
LOG_LEVEL=INFO
DEFAULT_TRADE_SIZE=10
```

### For Live Trading (add these when ready):
```env
POLYGON_WALLET_PRIVATE_KEY=your_key
POLYMARKET_API_KEY=your_key
POLYMARKET_SECRET=your_secret
POLYMARKET_PASSPHRASE=your_passphrase
OPENAI_API_KEY=your_key  # For AI predictions
```

## Troubleshooting

### Backend not responding externally
1. Check service: `sudo systemctl status polymarket-bot`
2. Check firewall: `gcloud compute firewall-rules list --filter="allowed:tcp:8000"`
3. Restart: `sudo systemctl restart polymarket-bot`

### Frontend shows no data
1. Check backend is running (curl test above)
2. Hard refresh browser (Ctrl+Shift+R)
3. Trigger redeploy on Netlify

### Backend crashes repeatedly
1. Check logs: `sudo journalctl -u polymarket-bot -n 100`
2. Check memory: `free -h` (e2-micro has limited RAM)
3. May need to restart VM if OOM
