# Polymarket Trading Bot - Backend

FastAPI backend for the Polymarket trading bot with AI predictions.

## Quick Start

```bash
cd backend
pip install -r requirements.txt
python main.py
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Health check |
| GET | `/api/markets` | Get active markets |
| GET | `/api/markets/{id}` | Get specific market |
| GET | `/api/status` | Get bot status |
| GET | `/api/activity` | Get activity log |
| POST | `/api/bot/start` | Start trading bot |
| POST | `/api/bot/stop` | Stop trading bot |
| POST | `/api/analyze/{id}` | AI market analysis |
| POST | `/api/trade` | Execute trade |
| GET | `/api/stats/summary` | Trading statistics |
| WS | `/ws` | Real-time WebSocket |

## API Documentation

When running, visit: http://localhost:8000/docs

## Deployment

### Railway
```bash
railway login
railway init
railway up
```

### Render
1. Connect GitHub repo
2. Set build command: `pip install -r backend/requirements.txt`
3. Set start command: `cd backend && python main.py`
4. Deploy!

### Docker
```bash
docker build -t polymarket-bot .
docker run -p 8000:8000 polymarket-bot
```
