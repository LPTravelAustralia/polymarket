#!/usr/bin/env python3
"""
FastAPI Backend for Polymarket Trading Bot
Production-ready API with WebSocket support
"""
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, BackgroundTasks
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
    app.state.bot_stats = {
        "trades_today": 0,
        "total_pnl": 0.0,
        "win_rate": 0.0,
        "active_positions": 0
    }
    app.state.activity_log = []
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


@app.post("/api/bot/start")
async def start_bot(background_tasks: BackgroundTasks):
    """Start the trading bot"""
    if app.state.bot_running:
        raise HTTPException(status_code=400, detail="Bot already running")
    
    app.state.bot_running = True
    add_activity("🚀 Bot started")
    
    # In production, start background trading loop here
    await broadcast_update({"type": "status", "running": True})
    
    return {"success": True, "message": "Bot started"}


@app.post("/api/bot/stop")
async def stop_bot():
    """Stop the trading bot"""
    if not app.state.bot_running:
        raise HTTPException(status_code=400, detail="Bot not running")
    
    app.state.bot_running = False
    add_activity("🛑 Bot stopped")
    
    await broadcast_update({"type": "status", "running": False})
    
    return {"success": True, "message": "Bot stopped"}


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
            "uptime": "0h 0m"  # Calculate in production
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
