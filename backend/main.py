#!/usr/bin/env python3
"""
FastAPI Backend for Polymarket Trading Bot
Production-ready API with WebSocket support
"""
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
from contextlib import asynccontextmanager
import asyncio
import json
import os
import sys
from pathlib import Path
from collections import deque

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.gamma_client import GammaMarketClient
from src.core.config import load_config

# ============================================================================
# App Configuration
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    print("🚀 Starting Polymarket Trading Bot API...")
    # Initialize clients
    app.state.gamma_client = GammaMarketClient()
    app.state.bot_running = False
    app.state.bot_task = None
    app.state.bot_config: Optional[Any] = None
    app.state.bot_stats = {
        "trades_today": 0,
        "total_pnl": 0.0,
        "win_rate": 0.0,
        "active_positions": 0
    }
    app.state.activity_log = []
    app.state.positions: Dict[str, Dict[str, Any]] = {}
    app.state.trades: List[Dict[str, Any]] = []
    app.state.price_history: Dict[str, deque] = {}
    app.state.equity_history: List[Dict[str, Any]] = []  # For charting
    app.state.equity_start = 0.0
    app.state.equity_peak = 0.0
    app.state.connected_clients: List[WebSocket] = []
    yield
    print("👋 Shutting down...")


app = FastAPI(
    title="Polymarket Trading Bot API",
    description="AI-powered prediction market trading bot",
    version="1.0.0",
    lifespan=lifespan
)

# CORS - Allow frontend to connect
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # Next.js dev
        "http://localhost:8080",
        "https://*.vercel.app",   # Vercel deployments
        "https://*.netlify.app",  # Netlify deployments
        "*"  # Allow all for development
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Models
# ============================================================================

class MarketResponse(BaseModel):
    id: str
    question: str
    liquidity: float
    volume: float
    yes_price: float
    no_price: float
    end_date: Optional[str] = None
    category: Optional[str] = None
    slug: Optional[str] = None


class BotStatus(BaseModel):
    running: bool
    trades_today: int
    total_pnl: float
    win_rate: float
    active_positions: int
    last_update: Optional[str] = None


class TradeRequest(BaseModel):
    market_id: str
    side: str  # "yes" or "no"
    amount: float
    
    
class AnalysisResponse(BaseModel):
    market_id: str
    question: str
    recommendation: str  # BUY_YES, BUY_NO, HOLD
    confidence: float
    predicted_probability: float
    reasoning: str
    edge: float


class BotConfig(BaseModel):
    """Runtime configuration for the paper-trading loop"""
    trade_size: float = 25.0
    max_markets: int = 5
    per_market_cap: float = 100.0
    global_cap: float = 500.0
    drawdown_limit: float = 200.0
    poll_interval: int = 20
    agent: str = "momentum"  # momentum | ai
    markets: Optional[List[str]] = None  # Optional allowlist of markets to trade


class PositionSnapshot(BaseModel):
    market_id: str
    question: str
    side: str
    size: float
    entry_price: float
    mark_price: float
    unrealized_pnl: float
    last_update: str


class PortfolioState(BaseModel):
    positions: List[PositionSnapshot]
    trades: List[Dict[str, Any]]
    total_pnl: float
    exposure: float


# ============================================================================
# Helper Functions
# ============================================================================

def add_activity(message: str):
    """Add to activity log"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    entry = f"[{timestamp}] {message}"
    app.state.activity_log.insert(0, entry)
    app.state.activity_log = app.state.activity_log[:100]  # Keep last 100


def parse_market(m: dict) -> MarketResponse:
    """Parse raw market data into response model"""
    # Parse prices
    yes_price, no_price = 0.5, 0.5
    try:
        prices = json.loads(m.get("outcomePrices", "[0.5, 0.5]"))
        yes_price = float(prices[0]) if prices else 0.5
        no_price = float(prices[1]) if len(prices) > 1 else 0.5
    except:
        pass
    
    return MarketResponse(
        id=m.get("condition_id", m.get("id", "")),
        question=m.get("question", "Unknown"),
        liquidity=float(m.get("liquidity", 0)),
        volume=float(m.get("volume", 0)),
        yes_price=yes_price,
        no_price=no_price,
        end_date=m.get("end_date_iso"),
        category=m.get("category"),
        slug=m.get("slug")
    )


async def broadcast_update(data: dict):
    """Broadcast to all connected WebSocket clients"""
    for client in app.state.connected_clients:
        try:
            await client.send_json(data)
        except:
            pass


def _current_exposure() -> float:
    """Return total notional exposure of open positions"""
    exposure = 0.0
    for pos in app.state.positions.values():
        exposure += float(pos.get("size", 0)) * float(pos.get("entry_price", 0))
    return exposure


def _per_market_exposure(market_id: str) -> float:
    pos = app.state.positions.get(market_id)
    if not pos:
        return 0.0
    return float(pos.get("size", 0)) * float(pos.get("entry_price", 0))


def _update_price_history(market_id: str, price: float):
    history = app.state.price_history.get(market_id)
    if not history:
        history = deque(maxlen=5)
        app.state.price_history[market_id] = history
    history.append(price)


def _momentum_signal(market: MarketResponse) -> Optional[str]:
    """Pick markets with prices in tradeable range where movement matters"""
    # Only trade markets with prices between 20% and 80% - these have real movement
    if market.yes_price < 0.20 or market.yes_price > 0.80:
        return None
    
    # Need some liquidity (lowered for demo)
    if market.liquidity < 1000:
        return None
    
    history = app.state.price_history.get(market.id, deque())
    
    # Momentum: if price is rising, go YES; if falling, go NO
    if len(history) >= 2:
        delta = history[-1] - history[-2]
        if delta > 0.005:  # Price rising
            return "yes"
        if delta < -0.005:  # Price falling
            return "no"
    
    # Mean reversion: bet against extremes within our range
    if market.yes_price < 0.40:
        return "yes"  # Underpriced, bet it goes up
    if market.yes_price > 0.60:
        return "no"  # Overpriced, bet it goes down
    
    return None


def _mark_positions(markets: Dict[str, MarketResponse]) -> float:
    """Mark positions to market and return total unrealized PnL"""
    total_pnl = 0.0
    for mid, pos in list(app.state.positions.items()):
        market = markets.get(mid)
        if not market:
            continue
        side = pos.get("side")
        entry = float(pos.get("entry_price", 0))
        size = float(pos.get("size", 0))
        mark_price = market.yes_price if side == "yes" else market.no_price
        pnl = (mark_price - entry) * size if side == "yes" else (entry - mark_price) * size
        pos["unrealized_pnl"] = pnl
        pos["mark_price"] = mark_price
        pos["last_update"] = datetime.now().isoformat()
        total_pnl += pnl
    return total_pnl


async def _trading_loop(config: BotConfig):
    """Paper trading loop running while bot flag remains true"""
    add_activity(
        f"🤖 Paper trading loop: {config.agent} | size ${config.trade_size} | max {config.max_markets} markets"
    )
    app.state.equity_start = float(config.global_cap)
    app.state.equity_peak = app.state.equity_start
    gamma = app.state.gamma_client
    try:
        while app.state.bot_running:
            markets_raw = gamma.get_current_markets(limit=config.max_markets * 3)
            parsed_markets: Dict[str, MarketResponse] = {}

            # Prepare market map and update price history
            for raw in markets_raw:
                market = parse_market(raw)
                if config.markets and market.id not in config.markets:
                    continue
                parsed_markets[market.id] = market
                _update_price_history(market.id, market.yes_price)

            # Mark existing positions
            total_pnl = _mark_positions(parsed_markets)
            app.state.bot_stats["total_pnl"] = round(total_pnl, 2)
            app.state.bot_stats["active_positions"] = len(app.state.positions)
            app.state.bot_stats["trades_today"] = len(app.state.trades)

            # Simple drawdown check
            equity = app.state.equity_start + total_pnl
            app.state.equity_peak = max(app.state.equity_peak, equity)
            drawdown = app.state.equity_peak - equity
            if drawdown >= config.drawdown_limit:
                add_activity("⚠️ Drawdown limit hit - stopping bot")
                app.state.bot_running = False
                break

            # Consider new trades
            for market in list(parsed_markets.values())[: config.max_markets]:
                if market.id in app.state.positions:
                    continue
                if _current_exposure() + config.trade_size > config.global_cap:
                    break
                if _per_market_exposure(market.id) + config.trade_size > config.per_market_cap:
                    continue

                signal = _momentum_signal(market)
                if not signal:
                    continue

                entry_price = market.yes_price if signal == "yes" else market.no_price
                position = {
                    "market_id": market.id,
                    "question": market.question,
                    "side": signal,
                    "size": float(config.trade_size),
                    "entry_price": entry_price,
                    "mark_price": entry_price,
                    "unrealized_pnl": 0.0,
                    "opened_at": datetime.now().isoformat(),
                }
                app.state.positions[market.id] = position
                app.state.trades.insert(0, {
                    "market_id": market.id,
                    "question": market.question,
                    "side": signal,
                    "size": config.trade_size,
                    "entry_price": entry_price,
                    "timestamp": datetime.now().isoformat(),
                    "mode": "paper",
                })
                add_activity(
                    f"🟢 Entered {signal.upper()} ${config.trade_size} on {market.question[:42]}... at {entry_price:.2f}"
                )

            # Record equity snapshot for charting
            app.state.equity_history.append({
                "timestamp": datetime.now().isoformat(),
                "pnl": app.state.bot_stats["total_pnl"],
                "positions": len(app.state.positions),
                "exposure": _current_exposure(),
            })
            # Keep last 500 snapshots
            if len(app.state.equity_history) > 500:
                app.state.equity_history = app.state.equity_history[-500:]

            await broadcast_update({
                "type": "portfolio",
                "running": app.state.bot_running,
                "pnl": app.state.bot_stats["total_pnl"],
                "positions": list(app.state.positions.values()),
            })

            await asyncio.sleep(max(5, config.poll_interval))
    except asyncio.CancelledError:
        add_activity("⚠️ Trading loop cancelled")
    finally:
        add_activity("🛑 Paper trading loop stopped")


# ============================================================================
# REST API Endpoints
# ============================================================================

@app.get("/")
async def root():
    """Health check"""
    return {
        "status": "ok",
        "service": "Polymarket Trading Bot API",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat()
    }


@app.get("/api/markets", response_model=List[MarketResponse])
async def get_markets(
    limit: int = 20,
    category: Optional[str] = None,
    search: Optional[str] = None
):
    """Get active markets from Polymarket"""
    try:
        if search:
            markets = app.state.gamma_client.search_markets(search, limit=limit)
        else:
            markets = app.state.gamma_client.get_current_markets(limit=limit)
        
        result = [parse_market(m) for m in markets]
        
        # Filter by category if specified
        if category and category != "all":
            keywords = {
                "politics": ["trump", "biden", "election", "president", "congress"],
                "crypto": ["bitcoin", "btc", "ethereum", "crypto", "token"],
                "sports": ["nfl", "nba", "mlb", "super bowl", "championship"],
                "finance": ["fed", "rate", "inflation", "recession", "economy"]
            }
            kws = keywords.get(category.lower(), [])
            if kws:
                result = [m for m in result if any(kw in m.question.lower() for kw in kws)]
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/markets/{market_id}")
async def get_market(market_id: str):
    """Get a specific market by ID"""
    try:
        # For now, search in current markets
        markets = app.state.gamma_client.get_current_markets(limit=100)
        for m in markets:
            if m.get("condition_id") == market_id or m.get("id") == market_id:
                return parse_market(m)
        raise HTTPException(status_code=404, detail="Market not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/status", response_model=BotStatus)
async def get_status():
    """Get bot status"""
    return BotStatus(
        running=app.state.bot_running,
        trades_today=app.state.bot_stats["trades_today"],
        total_pnl=app.state.bot_stats["total_pnl"],
        win_rate=app.state.bot_stats["win_rate"],
        active_positions=app.state.bot_stats["active_positions"],
        last_update=datetime.now().isoformat()
    )


@app.get("/api/activity")
async def get_activity(limit: int = 20):
    """Get recent activity log"""
    return {"activities": app.state.activity_log[:limit]}


@app.get("/api/bot/portfolio", response_model=PortfolioState)
async def get_portfolio():
    """Return current paper-trading portfolio snapshot"""
    positions = []
    for pos in app.state.positions.values():
        positions.append(PositionSnapshot(
            market_id=pos.get("market_id"),
            question=pos.get("question", ""),
            side=pos.get("side", ""),
            size=float(pos.get("size", 0)),
            entry_price=float(pos.get("entry_price", 0)),
            mark_price=float(pos.get("mark_price", pos.get("entry_price", 0))),
            unrealized_pnl=float(pos.get("unrealized_pnl", 0)),
            last_update=pos.get("last_update", pos.get("opened_at", datetime.now().isoformat()))
        ))
    exposure = _current_exposure()
    return PortfolioState(
        positions=positions,
        trades=app.state.trades[:50],
        total_pnl=float(app.state.bot_stats.get("total_pnl", 0.0)),
        exposure=exposure
    )


@app.post("/api/bot/start")
async def start_bot(config: BotConfig):
    """Start the paper trading bot with runtime config"""
    if app.state.bot_running:
        raise HTTPException(status_code=400, detail="Bot already running")
    
    app.state.bot_running = True
    app.state.bot_config = config
    app.state.bot_stats["trades_today"] = 0
    app.state.trades = []
    app.state.positions = {}
    app.state.price_history = {}
    app.state.equity_history = []  # Reset chart data
    
    # Launch background loop
    app.state.bot_task = asyncio.create_task(_trading_loop(config))
    add_activity("🚀 Bot started")
    
    await broadcast_update({"type": "status", "running": True, "config": config.model_dump()})
    
    return {"success": True, "message": "Bot started", "config": config}


@app.post("/api/bot/stop")
async def stop_bot():
    """Stop the trading bot"""
    if not app.state.bot_running:
        raise HTTPException(status_code=400, detail="Bot not running")
    
    app.state.bot_running = False
    if app.state.bot_task:
        app.state.bot_task.cancel()
        app.state.bot_task = None
    add_activity("🛑 Bot stopped")
    
    await broadcast_update({"type": "status", "running": False})
    
    return {"success": True, "message": "Bot stopped"}


@app.get("/api/bot/equity-history")
async def get_equity_history():
    """Return PnL history for charting"""
    return {"history": app.state.equity_history}


@app.post("/api/analyze/{market_id}", response_model=AnalysisResponse)
async def analyze_market(market_id: str):
    """Analyze a market using AI (demo mode)"""
    try:
        # Get market
        markets = app.state.gamma_client.get_current_markets(limit=100)
        market = None
        for m in markets:
            if m.get("condition_id") == market_id or m.get("id") == market_id:
                market = m
                break
        
        if not market:
            raise HTTPException(status_code=404, detail="Market not found")
        
        # Parse current price
        yes_price = 0.5
        try:
            prices = json.loads(market.get("outcomePrices", "[0.5, 0.5]"))
            yes_price = float(prices[0])
        except:
            pass
        
        # Demo analysis (in production, use SuperforecasterAgent)
        # For now, return mock analysis
        import random
        predicted = yes_price + random.uniform(-0.15, 0.15)
        predicted = max(0.05, min(0.95, predicted))
        edge = predicted - yes_price
        
        if edge > 0.05:
            recommendation = "BUY_YES"
            reasoning = f"Market appears undervalued. Current price {yes_price:.0%} is below predicted probability of {predicted:.0%}."
        elif edge < -0.05:
            recommendation = "BUY_NO"
            reasoning = f"Market appears overvalued. Current price {yes_price:.0%} is above predicted probability of {predicted:.0%}."
        else:
            recommendation = "HOLD"
            reasoning = f"Market is fairly priced. Current {yes_price:.0%} is close to predicted {predicted:.0%}."
        
        add_activity(f"🔍 Analyzed: {market.get('question', 'Unknown')[:40]}...")
        
        return AnalysisResponse(
            market_id=market_id,
            question=market.get("question", "Unknown"),
            recommendation=recommendation,
            confidence=0.65 + random.uniform(0, 0.2),
            predicted_probability=predicted,
            reasoning=reasoning,
            edge=edge
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/trade")
async def execute_trade(trade: TradeRequest):
    """Execute a trade (demo mode - requires credentials for real trading)"""
    add_activity(f"📈 Trade requested: {trade.side.upper()} ${trade.amount} on market")
    
    # Check if we have credentials
    config = load_config()
    if not config.polygon_wallet_private_key:
        return {
            "success": False,
            "error": "Trading requires API credentials. Set POLYGON_WALLET_PRIVATE_KEY in .env",
            "demo_mode": True
        }
    
    # In production, execute real trade here
    return {
        "success": True,
        "message": "Trade executed (demo mode)",
        "trade": {
            "market_id": trade.market_id,
            "side": trade.side,
            "amount": trade.amount,
            "timestamp": datetime.now().isoformat()
        }
    }


# ============================================================================
# WebSocket for Real-time Updates
# ============================================================================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket for real-time updates"""
    await websocket.accept()
    app.state.connected_clients.append(websocket)
    
    try:
        # Send initial status
        await websocket.send_json({
            "type": "connected",
            "message": "Connected to Polymarket Bot",
            "running": app.state.bot_running
        })
        
        # Keep connection alive and handle messages
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30)
                # Handle incoming messages if needed
                msg = json.loads(data)
                
                if msg.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                    
            except asyncio.TimeoutError:
                # Send heartbeat
                await websocket.send_json({"type": "heartbeat"})
                
    except WebSocketDisconnect:
        pass
    finally:
        if websocket in app.state.connected_clients:
            app.state.connected_clients.remove(websocket)


# ============================================================================
# Stats Endpoints
# ============================================================================

@app.get("/api/stats/summary")
async def get_stats_summary():
    """Get trading statistics summary"""
    exposure = _current_exposure()
    return {
        "today": {
            "trades": app.state.bot_stats["trades_today"],
            "pnl": app.state.bot_stats["total_pnl"],
            "win_rate": app.state.bot_stats["win_rate"]
        },
        "positions": {
            "active": app.state.bot_stats["active_positions"],
            "pending": 0
        },
        "bot": {
            "status": "running" if app.state.bot_running else "stopped",
            "uptime": "0h 0m",  # Calculate in production
            "exposure": exposure,
            "config": app.state.bot_config.model_dump() if app.state.bot_config else None
        }
    }


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    port = int(os.environ.get("PORT", 8000))
    
    print("=" * 60)
    print("🤖 Polymarket Trading Bot - API Server")
    print("=" * 60)
    print(f"\n📡 API running at: http://localhost:{port}")
    print(f"📖 API docs at: http://localhost:{port}/docs")
    print(f"🔌 WebSocket at: ws://localhost:{port}/ws\n")
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=True
    )
