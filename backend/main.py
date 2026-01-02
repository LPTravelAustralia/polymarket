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
import sqlite3
import httpx
from pathlib import Path
from collections import deque

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.gamma_client import GammaMarketClient
from src.core.config import load_config

# AI API keys from environment
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# ============================================================================
# SQLite Persistence
# ============================================================================

DB_PATH = Path(__file__).parent / "trading_bot.db"


def init_db():
    """Initialize SQLite database with tables"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Positions table
    c.execute("""
        CREATE TABLE IF NOT EXISTS positions (
            market_id TEXT PRIMARY KEY,
            question TEXT,
            side TEXT,
            size REAL,
            entry_price REAL,
            mark_price REAL,
            unrealized_pnl REAL,
            opened_at TEXT,
            last_update TEXT
        )
    """)
    
    # Trades table (entry trades)
    c.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            market_id TEXT,
            question TEXT,
            side TEXT,
            size REAL,
            entry_price REAL,
            timestamp TEXT,
            mode TEXT
        )
    """)
    
    # Closed trades table
    c.execute("""
        CREATE TABLE IF NOT EXISTS closed_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            market_id TEXT,
            question TEXT,
            side TEXT,
            size REAL,
            entry_price REAL,
            exit_price REAL,
            pnl REAL,
            reason TEXT,
            opened_at TEXT,
            closed_at TEXT
        )
    """)
    
    # Stats table
    c.execute("""
        CREATE TABLE IF NOT EXISTS stats (
            key TEXT PRIMARY KEY,
            value REAL
        )
    """)
    
    conn.commit()
    conn.close()


def save_position(pos: Dict[str, Any]):
    """Save/update a position to DB"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT OR REPLACE INTO positions 
        (market_id, question, side, size, entry_price, mark_price, unrealized_pnl, opened_at, last_update)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        pos.get("market_id"),
        pos.get("question"),
        pos.get("side"),
        pos.get("size"),
        pos.get("entry_price"),
        pos.get("mark_price"),
        pos.get("unrealized_pnl", 0),
        pos.get("opened_at"),
        pos.get("last_update")
    ))
    conn.commit()
    conn.close()


def delete_position(market_id: str):
    """Remove a position from DB"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM positions WHERE market_id = ?", (market_id,))
    conn.commit()
    conn.close()


def save_trade(trade: Dict[str, Any]):
    """Save an entry trade to DB"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO trades (market_id, question, side, size, entry_price, timestamp, mode)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        trade.get("market_id"),
        trade.get("question"),
        trade.get("side"),
        trade.get("size"),
        trade.get("entry_price"),
        trade.get("timestamp"),
        trade.get("mode", "paper")
    ))
    conn.commit()
    conn.close()


def save_closed_trade(trade: Dict[str, Any]):
    """Save a closed trade to DB"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO closed_trades 
        (market_id, question, side, size, entry_price, exit_price, pnl, reason, opened_at, closed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        trade.get("market_id"),
        trade.get("question"),
        trade.get("side"),
        trade.get("size"),
        trade.get("entry_price"),
        trade.get("exit_price"),
        trade.get("pnl"),
        trade.get("reason"),
        trade.get("opened_at"),
        trade.get("closed_at")
    ))
    conn.commit()
    conn.close()


def save_stat(key: str, value: float):
    """Save a stat to DB"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO stats (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()


def load_state() -> Dict[str, Any]:
    """Load all state from DB"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # Load positions
    positions = {}
    for row in c.execute("SELECT * FROM positions"):
        pos = dict(row)
        positions[pos["market_id"]] = pos
    
    # Load trades
    trades = [dict(row) for row in c.execute("SELECT * FROM trades ORDER BY id DESC LIMIT 100")]
    
    # Load closed trades
    closed_trades = [dict(row) for row in c.execute("SELECT * FROM closed_trades ORDER BY id DESC LIMIT 100")]
    
    # Load stats
    stats = {}
    for row in c.execute("SELECT * FROM stats"):
        stats[row["key"]] = row["value"]
    
    conn.close()
    return {
        "positions": positions,
        "trades": trades,
        "closed_trades": closed_trades,
        "realized_pnl": stats.get("realized_pnl", 0.0)
    }

# ============================================================================
# App Configuration
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    print("🚀 Starting Polymarket Trading Bot API...")
    
    # Initialize SQLite
    init_db()
    saved = load_state()
    
    # Initialize clients
    app.state.gamma_client = GammaMarketClient()
    app.state.bot_running = False
    app.state.bot_task = None
    app.state.bot_config: Optional[Any] = None
    app.state.bot_stats = {
        "trades_today": 0,
        "total_pnl": 0.0,
        "win_rate": 0.0,
        "active_positions": len(saved["positions"])
    }
    app.state.activity_log = []
    app.state.positions: Dict[str, Dict[str, Any]] = saved["positions"]
    app.state.trades: List[Dict[str, Any]] = saved["trades"]
    app.state.closed_trades: List[Dict[str, Any]] = saved["closed_trades"]
    app.state.realized_pnl: float = saved["realized_pnl"]
    app.state.price_history: Dict[str, deque] = {}
    app.state.equity_history: List[Dict[str, Any]] = []  # For charting
    app.state.equity_start = 0.0
    app.state.equity_peak = 0.0
    app.state.connected_clients: List[WebSocket] = []
    
    if saved["positions"]:
        print(f"📂 Loaded {len(saved['positions'])} positions, ${saved['realized_pnl']:.2f} realized PnL")
    
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
    volume_24h: float = 0.0
    yes_price: float
    no_price: float
    spread: float = 0.0  # Difference between best bid and ask
    end_date: Optional[str] = None
    category: Optional[str] = None
    slug: Optional[str] = None
    closed: bool = False
    resolved_outcome: Optional[str] = None  # "yes", "no", or None if not resolved
    event_id: Optional[str] = None
    event_slug: Optional[str] = None
    description: Optional[str] = None
    image: Optional[str] = None


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


# Category keywords for filtering markets
CATEGORY_KEYWORDS = {
    'politics': ['trump', 'biden', 'election', 'congress', 'senate', 'president', 'vote', 'democrat', 'republican', 'governor', 'mayor', 'political', 'government', 'white house', 'impeach', 'gop', 'dnc', 'rnc', 'pelosi', 'mcconnell', 'desantis', 'newsom', 'vance', 'harris', 'pence'],
    'sports': ['nfl', 'nba', 'mlb', 'nhl', 'super bowl', 'world series', 'championship', 'playoff', 'football', 'basketball', 'baseball', 'hockey', 'soccer', 'tennis', 'golf', 'ufc', 'boxing', 'olympics', 'fifa', 'world cup', 'nfc', 'afc', 'mvp', 'touchdown', 'quarterback', 'lakers', 'warriors', 'celtics', 'yankees', 'dodgers', 'chiefs', 'eagles', 'cowboys', 'patriots', 'steelers', 'packers', 'bills', 'ravens', '49ers', 'rams', 'seahawks', 'broncos', 'texans', 'bears', 'lions', 'vikings', 'saints', 'falcons', 'panthers', 'buccaneers', 'cardinals', 'titans', 'colts', 'jaguars', 'bengals', 'browns', 'chargers', 'raiders', 'dolphins', 'jets', 'giants', 'commanders', 'thunder', 'heat', 'mavericks', 'suns', 'nuggets', 'clippers', 'grizzlies', 'pelicans', 'spurs', 'rockets', 'timberwolves', 'blazers', 'jazz', 'kings', 'hornets', 'hawks', 'bulls', 'cavaliers', 'pistons', 'pacers', 'bucks', 'magic', 'nets', 'knicks', 'sixers', 'raptors', 'wizards'],
    'crypto': ['bitcoin', 'btc', 'ethereum', 'eth', 'crypto', 'solana', 'sol', 'dogecoin', 'doge', 'xrp', 'ripple', 'cardano', 'ada', 'blockchain', 'defi', 'nft', 'binance', 'coinbase', 'microstrategy', 'saylor', 'altcoin', 'memecoin', 'meme coin', 'token', 'airdrop', 'staking', 'mining', 'halving', 'whale', 'hodl', 'satoshi', 'web3', 'polygon', 'matic', 'avalanche', 'avax', 'chainlink', 'link', 'uniswap', 'aave', 'maker', 'dai', 'usdc', 'usdt', 'tether', 'stablecoin', 'cbdc', 'lighter', 'megaeth', 'gta vi', 'gta 6'],
    'finance': ['fed', 'federal reserve', 'interest rate', 'stock', 'market', 's&p', 'nasdaq', 'dow', 'gdp', 'inflation', 'recession', 'bank', 'treasury', 'bond', 'ipo', 'earnings', 'tariff', 'deficit', 'debt ceiling', 'fomc', 'rate cut', 'rate hike', 'unemployment', 'jobs report', 'cpi', 'ppi'],
    'entertainment': ['movie', 'film', 'oscar', 'grammy', 'emmy', 'album', 'box office', 'netflix', 'disney', 'spotify', 'celebrity', 'actor', 'actress', 'singer', 'concert', 'award', 'taylor swift', 'drake', 'beyonce', 'marvel', 'dc', 'star wars', 'minecraft', 'zootopia', 'fantastic four', 'jurassic', 'pixar', 'dreamworks'],
    'tech': ['apple', 'google', 'microsoft', 'amazon', 'meta', 'facebook', 'twitter', 'x.com', 'elon', 'musk', 'ai', 'artificial intelligence', 'openai', 'chatgpt', 'tesla', 'spacex', 'iphone', 'android', 'nvidia', 'amd', 'intel', 'semiconductor', 'chip', 'starlink', 'neuralink', 'boring company', 'zuckerberg', 'pichai', 'nadella', 'cook', 'altman', 'sam altman'],
    'science': ['nasa', 'space', 'climate', 'vaccine', 'covid', 'health', 'fda', 'medicine', 'research', 'study', 'scientist', 'discovery', 'mars', 'moon', 'rocket', 'spacex', 'blue origin', 'artemis', 'asteroid', 'comet', 'earthquake', 'hurricane', 'tornado'],
    'world': ['ukraine', 'russia', 'china', 'war', 'nato', 'europe', 'asia', 'middle east', 'israel', 'gaza', 'iran', 'india', 'japan', 'uk', 'france', 'germany', 'canada', 'mexico', 'brazil', 'putin', 'zelensky', 'netanyahu', 'xi jinping', 'modi', 'macron', 'starmer', 'venezuela', 'maduro', 'taiwan', 'korea', 'kim jong'],
    'elections': ['2024', '2025', '2026', 'election', 'vote', 'ballot', 'poll', 'primary', 'caucus', 'electoral', 'swing state', 'battleground', 'midterm', 'runoff'],
    'ai': ['ai', 'artificial intelligence', 'openai', 'chatgpt', 'gpt', 'claude', 'anthropic', 'gemini', 'llm', 'machine learning', 'deep learning', 'neural', 'agi', 'superintelligence', 'grok', 'copilot', 'midjourney', 'stable diffusion', 'dall-e'],
}


def market_matches_categories(question: str, categories: List[str]) -> bool:
    """Check if a market question matches any of the specified categories"""
    if not categories:
        return True  # No filter = match all
    
    question_lower = question.lower()
    for category in categories:
        if category in CATEGORY_KEYWORDS:
            for keyword in CATEGORY_KEYWORDS[category]:
                if keyword in question_lower:
                    return True
    return False


class BotConfig(BaseModel):
    """Runtime configuration for the paper-trading loop"""
    trade_size: float = 25.0
    max_markets: int = 5
    per_market_cap: float = 100.0
    global_cap: float = 500.0
    drawdown_limit: float = 200.0
    poll_interval: int = 20
    agent: str = "momentum"  # momentum | ai | arbitrage | value | news | combined
    markets: Optional[List[str]] = None  # Optional allowlist of market IDs
    take_profit: float = 0.15  # Close position at +15% gain
    stop_loss: float = 0.10  # Close position at -10% loss
    # Category filter
    categories: Optional[List[str]] = None  # Filter by category: politics, sports, crypto, etc.
    # Liquidity/Volume filters
    min_liquidity: float = 1000.0  # Minimum liquidity in USD
    min_volume: float = 0.0  # Minimum 24h volume
    max_spread: float = 0.50  # Maximum bid-ask spread (0.50 = 50%)
    # Kelly Criterion sizing
    use_kelly_sizing: bool = False  # Use Kelly Criterion for position sizing
    kelly_fraction: float = 0.25  # Fraction of Kelly to use (0.25 = quarter Kelly)
    min_edge: float = 0.05  # Minimum edge required to trade (5%)
    # Momentum settings
    use_price_momentum: bool = True  # Consider price momentum
    momentum_period: int = 5  # Number of price samples for momentum
    # Volume filter
    use_volume_filter: bool = False  # Filter by volume spikes
    volume_spike_threshold: float = 2.0  # Multiple of avg volume
    min_volume_24h: float = 0.0  # Minimum 24h volume required (0 = disabled)
    # Other
    auto_exit_on_resolution: bool = True  # Auto-exit when market resolves
    time_to_expiry_filter: int = 0  # Minimum hours until expiry (0 = disabled)
    # Volatility filter
    min_volatility: float = 0.0  # Minimum price volatility (0 = disabled)
    prefer_active_markets: bool = True  # Prefer markets with recent activity


class PositionSnapshot(BaseModel):
    market_id: str
    question: str
    side: str
    size: float
    entry_price: float
    mark_price: float
    unrealized_pnl: float
    last_update: str


class TradingStats(BaseModel):
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    best_trade: float = 0.0
    worst_trade: float = 0.0
    profit_factor: float = 0.0


class PortfolioState(BaseModel):
    positions: List[PositionSnapshot]
    trades: List[Dict[str, Any]]
    closed_trades: List[Dict[str, Any]] = []
    total_pnl: float
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    exposure: float
    stats: Optional[TradingStats] = None


# ============================================================================
# Helper Functions
# ============================================================================

def add_activity(message: str):
    """Add to activity log"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    entry = f"[{timestamp}] {message}"
    app.state.activity_log.insert(0, entry)
    app.state.activity_log = app.state.activity_log[:100]  # Keep last 100


def calculate_stats(closed_trades: List[Dict[str, Any]]) -> TradingStats:
    """Calculate trading statistics from closed trades"""
    if not closed_trades:
        return TradingStats()
    
    wins = [t for t in closed_trades if t.get("pnl", 0) > 0]
    losses = [t for t in closed_trades if t.get("pnl", 0) < 0]
    
    total_trades = len(closed_trades)
    winning_trades = len(wins)
    losing_trades = len(losses)
    
    win_rate = winning_trades / total_trades if total_trades > 0 else 0
    
    avg_win = sum(t.get("pnl", 0) for t in wins) / len(wins) if wins else 0
    avg_loss = sum(t.get("pnl", 0) for t in losses) / len(losses) if losses else 0
    
    all_pnls = [t.get("pnl", 0) for t in closed_trades]
    best_trade = max(all_pnls) if all_pnls else 0
    worst_trade = min(all_pnls) if all_pnls else 0
    
    gross_profit = sum(t.get("pnl", 0) for t in wins)
    gross_loss = abs(sum(t.get("pnl", 0) for t in losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf') if gross_profit > 0 else 0
    
    return TradingStats(
        total_trades=total_trades,
        winning_trades=winning_trades,
        losing_trades=losing_trades,
        win_rate=round(win_rate * 100, 1),
        avg_win=round(avg_win, 2),
        avg_loss=round(avg_loss, 2),
        best_trade=round(best_trade, 2),
        worst_trade=round(worst_trade, 2),
        profit_factor=round(profit_factor, 2) if profit_factor != float('inf') else 999.99
    )


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
    
    # Calculate spread (difference from 50/50)
    spread = abs(yes_price - 0.5) * 2  # 0 = 50/50, 1 = certain
    
    # Parse 24h volume if available
    volume_24h = float(m.get("volume24hr", 0) or 0)
    
    # Check if market is closed/resolved
    is_closed = m.get("closed", False)
    resolved_outcome = None
    if is_closed:
        # If YES price is 1, YES won; if NO price is 1, NO won
        if yes_price >= 0.99:
            resolved_outcome = "yes"
        elif no_price >= 0.99:
            resolved_outcome = "no"
    
    return MarketResponse(
        id=m.get("conditionId", m.get("id", "")),
        question=m.get("question", "Unknown"),
        liquidity=float(m.get("liquidity", 0)),
        volume=float(m.get("volume", 0)),
        volume_24h=volume_24h,
        yes_price=yes_price,
        no_price=no_price,
        spread=round(spread, 4),
        end_date=m.get("endDateIso") or m.get("end_date_iso"),
        category=m.get("category"),
        slug=m.get("slug"),
        closed=is_closed,
        resolved_outcome=resolved_outcome,
        event_id=m.get("eventId") or m.get("event_id"),
        event_slug=m.get("eventSlug") or m.get("event_slug"),
        description=m.get("description"),
        image=m.get("image")
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
        history = deque(maxlen=20)  # Increased for better momentum detection
        app.state.price_history[market_id] = history
    history.append(price)


def _calculate_volatility(market_id: str) -> float:
    """Calculate price volatility from history"""
    history = app.state.price_history.get(market_id)
    if not history or len(history) < 3:
        return 0.0
    prices = list(history)
    if len(prices) < 2:
        return 0.0
    # Calculate standard deviation of price changes
    changes = [abs(prices[i] - prices[i-1]) for i in range(1, len(prices))]
    avg_change = sum(changes) / len(changes) if changes else 0
    return avg_change


def _value_signal(market: MarketResponse) -> Optional[str]:
    """Value betting strategy - find mispriced markets"""
    # Trade markets with prices in tradeable range
    if market.yes_price < 0.10 or market.yes_price > 0.90:
        return None
    
    if market.liquidity < 1000:
        return None
    
    # Look for markets with high spread (potential inefficiency)
    spread = abs(market.yes_price + market.no_price - 1.0)
    if spread > 0.02:  # >2% spread suggests mispricing
        # Bet on the side that seems underpriced
        if market.yes_price < 0.50:
            return "yes"  # YES seems cheap
        else:
            return "no"  # NO seems cheap
    
    # Look for extreme volume relative to liquidity (lots of interest)
    if market.volume_24h and market.liquidity:
        volume_ratio = market.volume_24h / market.liquidity
        if volume_ratio > 0.5:  # High activity market
            # Bet with the recent flow (price direction)
            history = app.state.price_history.get(market.id, deque())
            if len(history) >= 2:
                if history[-1] > history[0]:
                    return "yes"
                elif history[-1] < history[0]:
                    return "no"
    
    return None


def _arbitrage_signal(market: MarketResponse) -> Optional[str]:
    """Arbitrage strategy - find markets where YES + NO != 100%"""
    if market.yes_price < 0.05 or market.yes_price > 0.95:
        return None
    
    if market.liquidity < 500:
        return None
    
    # Check for arbitrage opportunity
    total = market.yes_price + market.no_price
    
    # If total > 1.0, both sides are overpriced (rare)
    # If total < 1.0, there's a gap we can exploit
    if total < 0.98:  # 2%+ gap
        # Buy the cheaper side
        if market.yes_price < market.no_price:
            return "yes"
        else:
            return "no"
    elif total > 1.02:  # Overpriced, could short but we can't
        return None
    
    return None


def _combined_signal(market: MarketResponse) -> Optional[str]:
    """Combined multi-strategy signal"""
    signals = []
    weights = []
    
    # Get momentum signal
    mom = _momentum_signal(market)
    if mom:
        signals.append(1 if mom == "yes" else -1)
        weights.append(0.4)  # 40% weight
    
    # Get value signal
    val = _value_signal(market)
    if val:
        signals.append(1 if val == "yes" else -1)
        weights.append(0.35)  # 35% weight
    
    # Get arbitrage signal
    arb = _arbitrage_signal(market)
    if arb:
        signals.append(1 if arb == "yes" else -1)
        weights.append(0.25)  # 25% weight
    
    if not signals:
        return None
    
    # Weighted average
    weighted_sum = sum(s * w for s, w in zip(signals, weights))
    total_weight = sum(weights)
    
    if total_weight > 0:
        score = weighted_sum / total_weight
        if score > 0.3:
            return "yes"
        elif score < -0.3:
            return "no"
    
    return None


async def _news_signal(market: MarketResponse) -> Optional[str]:
    """
    News-based signal - requires NEWSAPI_KEY environment variable.
    Analyzes recent news sentiment related to the market question.
    Falls back to momentum if news API is not available.
    """
    import os
    if not os.getenv("NEWSAPI_KEY"):
        # Fall back to momentum when API key not available
        return _momentum_signal(market)
    
    try:
        from src.connectors.news import NewsConnector
        connector = NewsConnector()
        
        # Extract key terms from market question
        question = market.question.lower()
        keywords = []
        for word in question.split():
            if len(word) > 3 and word not in ['will', 'what', 'when', 'does', 'have', 'been', 'this', 'that', 'with', 'from']:
                keywords.append(word)
        
        if not keywords:
            return _momentum_signal(market)
        
        # Search for news articles
        articles = connector.search(query=" ".join(keywords[:5]), limit=5)
        
        if not articles:
            return _momentum_signal(market)
        
        # Simple sentiment analysis based on keywords
        positive_words = ['win', 'success', 'approve', 'pass', 'rise', 'gain', 'positive', 'likely', 'expected', 'confirm']
        negative_words = ['lose', 'fail', 'reject', 'drop', 'fall', 'negative', 'unlikely', 'denied', 'cancel']
        
        sentiment_score = 0
        for article in articles:
            content = f"{article.get('title', '')} {article.get('description', '')}".lower()
            for word in positive_words:
                sentiment_score += content.count(word)
            for word in negative_words:
                sentiment_score -= content.count(word)
        
        # Bias toward YES if positive news, NO if negative
        if sentiment_score > 2:
            return "yes"
        elif sentiment_score < -2:
            return "no"
        
        # Neutral or mixed news - use momentum as tie-breaker
        return _momentum_signal(market)
        
    except Exception as e:
        logger.warning(f"News signal error: {e}")
        return _momentum_signal(market)


def _momentum_signal(market: MarketResponse) -> Optional[str]:
    """Pick markets with prices in tradeable range where movement matters"""
    # Trade markets with prices between 5% and 95% - very wide for demo
    if market.yes_price < 0.05 or market.yes_price > 0.95:
        return None
    
    # Minimal liquidity requirement for demo
    if market.liquidity < 100:
        return None
    
    history = app.state.price_history.get(market.id, deque())
    
    # Momentum: if price is rising, go YES; if falling, go NO
    if len(history) >= 2:
        delta = history[-1] - history[-2]
        if delta > 0.003:  # Price rising
            return "yes"
        if delta < -0.003:  # Price falling
            return "no"
    
    # Mean reversion / value bet on first pass
    if market.yes_price < 0.50:
        return "yes"  # Below fair value, bet YES
    else:
        return "no"  # Above fair value, bet NO


async def _ai_signal(market: MarketResponse) -> Optional[str]:
    """Use AI (Claude/GPT) to analyze market and generate trading signal"""
    # Trade markets with prices between 10% and 90%
    if market.yes_price < 0.10 or market.yes_price > 0.90:
        return None
    
    if market.liquidity < 500:
        return None
    
    # Build the prompt
    prompt = f"""You are an expert prediction market trader. Analyze this market and decide whether to bet YES or NO.

MARKET: {market.question}
CURRENT YES PRICE: {market.yes_price:.2%} (${market.yes_price:.2f})
CURRENT NO PRICE: {market.no_price:.2%} (${market.no_price:.2f})
LIQUIDITY: ${market.liquidity:,.0f}

Consider:
1. Is the current price fair based on available information?
2. What is your estimated probability this resolves YES?
3. Is there edge (difference between your estimate and market price)?

If you believe YES is underpriced (your probability > market price), respond with: BUY_YES
If you believe NO is underpriced (your probability < market price), respond with: BUY_NO
If no clear edge, respond with: HOLD

Respond with ONLY one of: BUY_YES, BUY_NO, or HOLD
No explanation needed, just the action."""

    try:
        # Try Anthropic first
        if ANTHROPIC_API_KEY:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": ANTHROPIC_API_KEY,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json"
                    },
                    json={
                        "model": "claude-3-haiku-20240307",
                        "max_tokens": 50,
                        "messages": [{"role": "user", "content": prompt}]
                    },
                    timeout=30
                )
                if resp.status_code == 200:
                    data = resp.json()
                    text = data.get("content", [{}])[0].get("text", "").strip().upper()
                    add_activity(f"🤖 AI analyzed: {market.question[:40]}... → {text}")
                    if "BUY_YES" in text:
                        return "yes"
                    elif "BUY_NO" in text:
                        return "no"
                    return None
        
        # Fallback to OpenAI
        if OPENAI_API_KEY:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {OPENAI_API_KEY}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "gpt-3.5-turbo",
                        "max_tokens": 50,
                        "messages": [{"role": "user", "content": prompt}]
                    },
                    timeout=30
                )
                if resp.status_code == 200:
                    data = resp.json()
                    text = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip().upper()
                    add_activity(f"🤖 AI analyzed: {market.question[:40]}... → {text}")
                    if "BUY_YES" in text:
                        return "yes"
                    elif "BUY_NO" in text:
                        return "no"
                    return None
        
        # No AI available, fall back to momentum
        add_activity("⚠️ No AI API key configured, using momentum signal")
        return _momentum_signal(market)
        
    except Exception as e:
        add_activity(f"⚠️ AI error: {str(e)[:50]}")
        return _momentum_signal(market)


async def _mark_positions(markets: Dict[str, MarketResponse], config: BotConfig) -> float:
    """Mark positions to market, check TP/SL and resolution, return total unrealized PnL"""
    total_pnl = 0.0
    positions_to_close = []
    
    for mid, pos in list(app.state.positions.items()):
        market = markets.get(mid)
        if not market:
            continue
        side = pos.get("side")
        entry = float(pos.get("entry_price", 0))
        size = float(pos.get("size", 0))
        
        # Check if market has resolved
        if market.closed and market.resolved_outcome:
            # Calculate final PnL based on resolution
            # If we bet on the winning side: payout = size (since shares pay $1)
            # If we bet on the losing side: payout = 0
            if market.resolved_outcome == side:
                # We won! Payout is $1 per share, we paid entry_price per share
                realized_pnl = (1.0 - entry) * size
                positions_to_close.append((mid, pos, realized_pnl, "RESOLVED_WIN"))
            else:
                # We lost. Payout is $0, we paid entry_price per share
                realized_pnl = -entry * size
                positions_to_close.append((mid, pos, realized_pnl, "RESOLVED_LOSS"))
            continue
        
        mark_price = market.yes_price if side == "yes" else market.no_price
        pnl = (mark_price - entry) * size if side == "yes" else (entry - mark_price) * size
        pos["unrealized_pnl"] = pnl
        pos["mark_price"] = mark_price
        pos["last_update"] = datetime.now().isoformat()
        total_pnl += pnl
        
        # Check take-profit / stop-loss
        pnl_pct = pnl / (entry * size) if entry * size > 0 else 0
        if pnl_pct >= config.take_profit:
            positions_to_close.append((mid, pos, pnl, "TP"))
        elif pnl_pct <= -config.stop_loss:
            positions_to_close.append((mid, pos, pnl, "SL"))
    
    # Close triggered positions
    for mid, pos, realized_pnl, reason in positions_to_close:
        if reason == "RESOLVED_WIN":
            emoji = "🏆"
            reason_display = "RESOLVED (WON)"
        elif reason == "RESOLVED_LOSS":
            emoji = "💀"
            reason_display = "RESOLVED (LOST)"
        elif reason == "TP":
            emoji = "🟢"
            reason_display = "TP"
        else:
            emoji = "🔴"
            reason_display = "SL"
            
        add_activity(f"{emoji} {reason_display} closed {pos['side'].upper()} on {pos['question'][:35]}... PnL: ${realized_pnl:+.2f}")
        
        # Record closed trade
        closed_trade = {
            "market_id": mid,
            "question": pos.get("question", ""),
            "side": pos.get("side"),
            "size": pos.get("size"),
            "entry_price": pos.get("entry_price"),
            "exit_price": 1.0 if reason == "RESOLVED_WIN" else (0.0 if reason == "RESOLVED_LOSS" else pos.get("mark_price")),
            "pnl": realized_pnl,
            "reason": reason,
            "opened_at": pos.get("opened_at"),
            "closed_at": datetime.now().isoformat(),
        }
        app.state.closed_trades.insert(0, closed_trade)
        save_closed_trade(closed_trade)  # Persist to DB
        
        app.state.realized_pnl += realized_pnl
        save_stat("realized_pnl", app.state.realized_pnl)  # Persist to DB
        
        # Remove from open positions
        del app.state.positions[mid]
        delete_position(mid)  # Remove from DB
        
        # Broadcast position close event
        await broadcast_update({
            "type": "close",
            "reason": reason,
            "trade": closed_trade,
            "realized_pnl": app.state.realized_pnl,
        })
    
    return total_pnl


def _calculate_kelly_size(config: BotConfig, market: MarketResponse, predicted_prob: float) -> float:
    """Calculate position size using Kelly Criterion"""
    if not config.use_kelly_sizing:
        return config.trade_size
    
    # Get current price as implied probability
    current_price = market.yes_price
    
    # Calculate edge
    edge = predicted_prob - current_price
    if abs(edge) < config.min_edge:
        return 0.0  # No trade if edge too small
    
    # Kelly formula: f* = (bp - q) / b
    # Where b = odds, p = win prob, q = lose prob
    if edge > 0:  # Bet YES
        b = (1 - current_price) / current_price  # Odds for YES
        p = predicted_prob
    else:  # Bet NO
        b = current_price / (1 - current_price)  # Odds for NO
        p = 1 - predicted_prob
    
    q = 1 - p
    kelly_fraction_full = (b * p - q) / b if b > 0 else 0
    
    # Apply fractional Kelly
    kelly_size = config.global_cap * kelly_fraction_full * config.kelly_fraction
    
    # Clamp to reasonable bounds
    kelly_size = max(0, min(kelly_size, config.per_market_cap, config.trade_size * 3))
    
    return round(kelly_size, 2)


def _passes_filters(market: MarketResponse, config: BotConfig) -> bool:
    """Check if market passes all configured filters"""
    # Category filter
    if config.categories and len(config.categories) > 0:
        if not market_matches_categories(market.question, config.categories):
            return False
    
    # Liquidity filter
    if market.liquidity < config.min_liquidity:
        return False
    
    # Volume filter (legacy)
    if config.min_volume > 0 and (market.volume_24h or 0) < config.min_volume:
        return False
    
    # 24h volume filter (new)
    if config.min_volume_24h > 0 and (market.volume_24h or 0) < config.min_volume_24h:
        return False
    
    # Spread filter
    if market.spread is not None and market.spread > config.max_spread:
        return False
    
    # Price range filter (not at extremes)
    if market.yes_price < 0.05 or market.yes_price > 0.95:
        return False
    
    # Volatility filter - estimate from spread and price
    if config.min_volatility > 0:
        # Estimate volatility as spread relative to price midpoint
        midpoint = max(market.yes_price, 0.01)
        estimated_volatility = (market.spread or 0.05) / midpoint if market.spread else 0.05
        if estimated_volatility < config.min_volatility:
            return False
    
    # Time to expiry filter
    if config.time_to_expiry_filter > 0 and market.end_date:
        try:
            from datetime import timezone
            end_dt = datetime.fromisoformat(market.end_date.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            hours_remaining = (end_dt - now).total_seconds() / 3600
            if hours_remaining < config.time_to_expiry_filter:
                return False
        except:
            pass  # If we can't parse, allow the market
    
    return True


async def _trading_loop(config: BotConfig):
    """Paper trading loop running while bot flag remains true"""
    # Build descriptive startup message
    filters_desc = []
    if config.categories:
        filters_desc.append(f"categories: {', '.join(config.categories)}")
    if config.min_liquidity > 0:
        filters_desc.append(f"min liq ${config.min_liquidity:,.0f}")
    if config.use_kelly_sizing:
        filters_desc.append(f"Kelly {config.kelly_fraction:.0%}")
    
    filter_str = f" | filters: {', '.join(filters_desc)}" if filters_desc else ""
    add_activity(
        f"🤖 Paper trading: {config.agent} | ${config.trade_size}/trade | max {config.max_markets}{filter_str}"
    )
    
    app.state.equity_start = float(config.global_cap)
    app.state.equity_peak = app.state.equity_start
    gamma = app.state.gamma_client
    try:
        while app.state.bot_running:
            # Fetch many markets - increased limit for better coverage
            markets_raw = gamma.get_current_markets(limit=500)
            parsed_markets: Dict[str, MarketResponse] = {}

            # Prepare market map and update price history
            tradeable_count = 0
            filtered_count = 0
            for raw in markets_raw:
                market = parse_market(raw)
                # Apply market ID allowlist
                if config.markets and market.id not in config.markets:
                    continue
                # Apply all filters
                if not _passes_filters(market, config):
                    filtered_count += 1
                    continue
                parsed_markets[market.id] = market
                _update_price_history(market.id, market.yes_price)
                tradeable_count += 1
            
            # Also fetch closed markets where we have positions (for resolution detection)
            position_ids = list(app.state.positions.keys())
            missing_ids = [mid for mid in position_ids if mid not in parsed_markets]
            if missing_ids:
                # Fetch all markets (including closed) to check resolution status
                try:
                    all_markets_raw = gamma.get_markets(
                        querystring_params={"limit": 500}  # Get more to find our positions
                    )
                    for raw in all_markets_raw:
                        market = parse_market(raw)
                        if market.id in missing_ids:
                            parsed_markets[market.id] = market
                            add_activity(f"📡 Checking resolution status for: {market.question[:40]}...")
                except Exception as e:
                    add_activity(f"⚠️ Could not check resolution: {str(e)[:30]}")
            
            if not app.state.positions:  # Log once at start
                filter_msg = f" ({filtered_count} filtered out)" if filtered_count > 0 else ""
                add_activity(f"📊 Scanned {len(markets_raw)} markets, {tradeable_count} passed filters{filter_msg}")
            # Mark existing positions and check TP/SL
            total_pnl = await _mark_positions(parsed_markets, config)
            # Include realized PnL from closed trades
            total_pnl += app.state.realized_pnl
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

            # Consider new trades - iterate all markets to find tradeable ones
            trades_opened = 0
            for market in parsed_markets.values():
                if trades_opened >= config.max_markets:
                    break
                if market.id in app.state.positions:
                    continue
                
                # Calculate trade size (Kelly or fixed)
                if config.use_kelly_sizing:
                    # For Kelly, we need a probability estimate
                    # Use a simple momentum-based estimate for now
                    momentum = _momentum_signal(market)
                    if momentum == "yes":
                        predicted_prob = min(0.95, market.yes_price + 0.1)
                    elif momentum == "no":
                        predicted_prob = max(0.05, market.yes_price - 0.1)
                    else:
                        predicted_prob = market.yes_price
                    
                    trade_size = _calculate_kelly_size(config, market, predicted_prob)
                    if trade_size < 1.0:  # Skip if Kelly size too small
                        continue
                else:
                    trade_size = config.trade_size
                
                if _current_exposure() + trade_size > config.global_cap:
                    break
                if _per_market_exposure(market.id) + trade_size > config.per_market_cap:
                    continue

                # Get signal based on selected agent
                if config.agent == "ai":
                    signal = await _ai_signal(market)
                elif config.agent == "value":
                    signal = _value_signal(market)
                elif config.agent == "arbitrage":
                    signal = _arbitrage_signal(market)
                elif config.agent == "combined":
                    signal = _combined_signal(market)
                elif config.agent == "news":
                    signal = await _news_signal(market)
                else:  # momentum (default)
                    signal = _momentum_signal(market)
                    
                if not signal:
                    continue
                
                # Check minimum edge requirement
                if config.min_edge > 0:
                    current_price = market.yes_price if signal == "yes" else market.no_price
                    # Simple edge calculation: if we're betting YES at 0.4, we think it should be higher
                    implied_edge = 0.1 if signal == "yes" else 0.1  # Simplified
                    if implied_edge < config.min_edge:
                        continue

                entry_price = market.yes_price if signal == "yes" else market.no_price
                position = {
                    "market_id": market.id,
                    "question": market.question,
                    "side": signal,
                    "size": float(trade_size),
                    "entry_price": entry_price,
                    "mark_price": entry_price,
                    "unrealized_pnl": 0.0,
                    "opened_at": datetime.now().isoformat(),
                    "last_update": datetime.now().isoformat(),
                }
                app.state.positions[market.id] = position
                save_position(position)  # Persist to DB
                
                trade = {
                    "market_id": market.id,
                    "question": market.question,
                    "side": signal,
                    "size": trade_size,
                    "entry_price": entry_price,
                    "timestamp": datetime.now().isoformat(),
                    "mode": "paper",
                }
                app.state.trades.insert(0, trade)
                save_trade(trade)  # Persist to DB
                
                trades_opened += 1
                kelly_note = " (Kelly)" if config.use_kelly_sizing else ""
                add_activity(
                    f"🟢 Entered {signal.upper()} ${trade_size}{kelly_note} on {market.question[:38]}... at {entry_price:.2f}"
                )
                
                # Broadcast new trade event
                await broadcast_update({
                    "type": "trade",
                    "trade": trade,
                    "position": position,
                })

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


class MarketsResponse(BaseModel):
    """Response for markets endpoint with metadata"""
    markets: List[MarketResponse]
    total: int
    showing: int


@app.get("/api/markets")
async def get_markets(
    limit: int = 50,
    offset: int = 0,
    category: Optional[str] = None,
    search: Optional[str] = None,
    sort_by: str = "volume"  # volume, liquidity, end_date
):
    """Get active markets from Polymarket with filtering and sorting"""
    try:
        # Fetch more markets for better filtering (we'll paginate client-side)
        fetch_limit = max(500, limit * 3)
        
        if search:
            raw_markets = app.state.gamma_client.search_markets(search, limit=fetch_limit)
        else:
            raw_markets = app.state.gamma_client.get_current_markets(limit=fetch_limit)
        
        # Parse all markets
        parsed = [parse_market(m) for m in raw_markets]
        
        # Filter out expired markets (end_date in the past)
        now = datetime.now().isoformat()
        active_markets = [
            m for m in parsed 
            if not m.end_date or m.end_date > now
        ]
        
        # Filter by category if specified
        if category and category != "all":
            keywords = {
                "politics": ["trump", "biden", "election", "president", "congress", "senate", "governor", "vote"],
                "crypto": ["bitcoin", "btc", "ethereum", "eth", "crypto", "token", "solana", "xrp"],
                "sports": ["nfl", "nba", "mlb", "nhl", "super bowl", "championship", "win", "playoff", "bowl"],
                "finance": ["fed", "rate", "inflation", "recession", "economy", "gdp", "deficit", "tariff"]
            }
            kws = keywords.get(category.lower(), [])
            if kws:
                active_markets = [m for m in active_markets if any(kw in m.question.lower() for kw in kws)]
        
        # Sort markets
        if sort_by == "volume":
            active_markets.sort(key=lambda x: x.volume, reverse=True)
        elif sort_by == "liquidity":
            active_markets.sort(key=lambda x: x.liquidity, reverse=True)
        elif sort_by == "end_date":
            active_markets.sort(key=lambda x: x.end_date or "9999")
        
        total = len(active_markets)
        paginated = active_markets[offset:offset + limit]
        
        return {
            "markets": paginated,
            "total": total,
            "showing": len(paginated)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/selectable-markets")
async def get_selectable_markets(
    limit: int = 100,
    category: Optional[str] = None,
    min_liquidity: float = 1000.0,
    search: Optional[str] = None
):
    """
    Get markets available for manual selection.
    Returns markets sorted by volume, filtered for activity and liquidity.
    Designed for populating a market selection UI.
    """
    try:
        fetch_limit = 500
        
        if search:
            raw_markets = app.state.gamma_client.search_markets(search, limit=fetch_limit)
        else:
            raw_markets = app.state.gamma_client.get_current_markets(limit=fetch_limit)
        
        parsed = [parse_market(m) for m in raw_markets]
        
        # Filter out expired markets
        now = datetime.now().isoformat()
        active_markets = [m for m in parsed if not m.end_date or m.end_date > now]
        
        # Filter by liquidity
        active_markets = [m for m in active_markets if m.liquidity >= min_liquidity]
        
        # Filter out extreme prices (effectively resolved)
        active_markets = [m for m in active_markets if 0.05 <= m.yes_price <= 0.95]
        
        # Filter by category if specified
        if category and category != "all":
            active_markets = [m for m in active_markets if market_matches_categories(m.question, [category])]
        
        # Sort by volume (most active first)
        active_markets.sort(key=lambda x: x.volume, reverse=True)
        
        # Limit results
        paginated = active_markets[:limit]
        
        return {
            "markets": [
                {
                    "id": m.id,
                    "question": m.question,
                    "volume": m.volume,
                    "liquidity": m.liquidity,
                    "yes_price": m.yes_price,
                    "volume_24h": m.volume_24h
                }
                for m in paginated
            ],
            "total": len(active_markets),
            "showing": len(paginated)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/markets/{market_id}")
async def get_market(market_id: str):
    """Get a specific market by ID"""
    try:
        # Try to get market by ID directly from Gamma API
        if market_id.isdigit():
            market = app.state.gamma_client.get_market(int(market_id))
            if market:
                return parse_market(market)
        
        # Search in current markets (use more markets and correct field name)
        markets = app.state.gamma_client.get_current_markets(limit=500)
        for m in markets:
            # Gamma API uses conditionId (camelCase), not condition_id
            if m.get("conditionId") == market_id or str(m.get("id")) == market_id:
                return parse_market(m)
        raise HTTPException(status_code=404, detail="Market not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class EventResponse(BaseModel):
    """Event with grouped markets"""
    id: str
    title: str
    slug: Optional[str] = None
    description: Optional[str] = None
    image: Optional[str] = None
    end_date: Optional[str] = None
    markets: List[MarketResponse] = []
    total_volume: float = 0.0
    total_liquidity: float = 0.0


class EventsResponse(BaseModel):
    """Response for events endpoint"""
    events: List[EventResponse]
    total: int
    showing: int


@app.get("/api/events")
async def get_events(
    limit: int = 20,
    offset: int = 0,
    search: Optional[str] = None,
    sort_by: str = "volume"  # volume, liquidity, end_date
):
    """Get events with grouped markets"""
    try:
        # Fetch events from Gamma API - events include embedded markets!
        raw_events = app.state.gamma_client.get_current_events(limit=200)
        
        # Filter out expired events
        now = datetime.now().isoformat()
        
        events = []
        for e in raw_events:
            event_id = str(e.get("id", ""))
            # Gamma API uses camelCase: endDate not end_date_iso
            end_date = e.get("endDate") or e.get("end_date_iso")
            
            # Skip expired events (compare date portion only)
            if end_date:
                end_date_str = end_date[:10] if len(end_date) >= 10 else end_date
                now_str = now[:10]
                if end_date_str < now_str:
                    continue
            
            # Skip if search doesn't match
            if search:
                title = e.get("title", "").lower()
                desc = (e.get("description") or "").lower()
                if search.lower() not in title and search.lower() not in desc:
                    continue
            
            # Get markets embedded in the event (Gamma API includes them)
            event_markets = e.get("markets", [])
            
            # Parse markets - filter out closed ones
            parsed_markets = []
            for m in event_markets:
                if m.get("closed", False):
                    continue
                parsed_markets.append(parse_market(m))
            
            # Use event-level volume/liquidity from Gamma API if available
            total_volume = float(e.get("volume", 0) or 0)
            total_liquidity = float(e.get("liquidity", 0) or 0)
            
            # Fall back to summing markets if not available
            if total_volume == 0 and parsed_markets:
                total_volume = sum(m.volume for m in parsed_markets)
            if total_liquidity == 0 and parsed_markets:
                total_liquidity = sum(m.liquidity for m in parsed_markets)
            
            events.append(EventResponse(
                id=event_id,
                title=e.get("title", "Unknown Event"),
                slug=e.get("slug"),
                description=e.get("description"),
                image=e.get("image"),
                end_date=end_date,
                markets=parsed_markets,
                total_volume=total_volume,
                total_liquidity=total_liquidity
            ))
        
        # Sort events
        if sort_by == "volume":
            events.sort(key=lambda x: x.total_volume, reverse=True)
        elif sort_by == "liquidity":
            events.sort(key=lambda x: x.total_liquidity, reverse=True)
        elif sort_by == "end_date":
            events.sort(key=lambda x: x.end_date or "9999")
        
        total = len(events)
        paginated = events[offset:offset + limit]
        
        return EventsResponse(
            events=paginated,
            total=total,
            showing=len(paginated)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/events/{event_id}")
async def get_event(event_id: str):
    """Get a specific event with its markets"""
    try:
        # Fetch the event
        event = app.state.gamma_client.get_event(int(event_id))
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")
        
        # Fetch markets for this event
        raw_markets = app.state.gamma_client.get_current_markets(limit=500)
        event_markets = [
            parse_market(m) for m in raw_markets
            if (m.get("event_id") or m.get("eventId") or "") == event_id
        ]
        
        now = datetime.now().isoformat()
        event_markets = [m for m in event_markets if not m.end_date or m.end_date > now]
        
        return EventResponse(
            id=event_id,
            title=event.get("title", "Unknown Event"),
            slug=event.get("slug"),
            description=event.get("description"),
            image=event.get("image"),
            end_date=event.get("end_date_iso"),
            markets=event_markets,
            total_volume=sum(m.volume for m in event_markets),
            total_liquidity=sum(m.liquidity for m in event_markets)
        )
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


# ============================================================================
# News & Search Endpoints
# ============================================================================

class NewsArticle(BaseModel):
    title: str
    description: Optional[str] = None
    url: str
    source: str
    published_at: str


class NewsResponse(BaseModel):
    articles: List[NewsArticle]
    query: str


class SearchResultItem(BaseModel):
    title: str
    url: str
    content: str
    score: float = 0.0


class SearchResponse(BaseModel):
    results: List[SearchResultItem]
    query: str


@app.get("/api/news")
async def get_news(query: str, limit: int = 10):
    """
    Get news articles relevant to a search query.
    Requires NEWSAPI_KEY environment variable.
    """
    try:
        from src.connectors.news import NewsConnector
        
        connector = NewsConnector()
        articles = connector.search(query, limit=limit)
        
        return NewsResponse(
            articles=[
                NewsArticle(
                    title=a.title,
                    description=a.description,
                    url=a.url,
                    source=a.source,
                    published_at=a.published_at
                )
                for a in articles
            ],
            query=query
        )
    except ImportError:
        raise HTTPException(status_code=501, detail="News connector not available")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/news/market/{market_id}")
async def get_market_news(market_id: str, limit: int = 5):
    """Get news articles relevant to a specific market"""
    try:
        from src.connectors.news import NewsConnector
        
        # Get the market
        markets = app.state.gamma_client.get_current_markets(limit=500)
        market = None
        for m in markets:
            if m.get("conditionId") == market_id or str(m.get("id")) == market_id:
                market = m
                break
        
        if not market:
            raise HTTPException(status_code=404, detail="Market not found")
        
        connector = NewsConnector()
        context = connector.get_market_context(
            market.get("question", ""),
            market.get("description"),
            limit=limit
        )
        
        articles = connector.search(market.get("question", ""), limit=limit)
        
        return {
            "market_id": market_id,
            "question": market.get("question"),
            "context": context,
            "articles": [
                {
                    "title": a.title,
                    "description": a.description,
                    "url": a.url,
                    "source": a.source,
                    "published_at": a.published_at
                }
                for a in articles
            ]
        }
    except ImportError:
        raise HTTPException(status_code=501, detail="News connector not available")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/search")
async def web_search(query: str, limit: int = 5):
    """
    Web search using Tavily or DuckDuckGo.
    Tavily requires TAVILY_API_KEY environment variable.
    """
    try:
        from src.connectors.search import TavilySearchConnector, DuckDuckGoSearchConnector
        
        # Try Tavily first (better quality)
        tavily = TavilySearchConnector()
        if tavily.api_key:
            results = tavily.search(query, max_results=limit)
        else:
            # Fallback to DuckDuckGo
            ddg = DuckDuckGoSearchConnector()
            results = ddg.search(query, max_results=limit)
        
        return SearchResponse(
            results=[
                SearchResultItem(
                    title=r.title,
                    url=r.url,
                    content=r.content,
                    score=r.score
                )
                for r in results
            ],
            query=query
        )
    except ImportError:
        raise HTTPException(status_code=501, detail="Search connector not available")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/activity")
async def get_activity(limit: int = 20):
    """Get recent activity log"""
    return {"activities": app.state.activity_log[:limit]}


@app.get("/api/bot/portfolio", response_model=PortfolioState)
async def get_portfolio():
    """Return current paper-trading portfolio snapshot"""
    positions = []
    unrealized = 0.0
    for pos in app.state.positions.values():
        pnl = float(pos.get("unrealized_pnl", 0))
        unrealized += pnl
        positions.append(PositionSnapshot(
            market_id=pos.get("market_id"),
            question=pos.get("question", ""),
            side=pos.get("side", ""),
            size=float(pos.get("size", 0)),
            entry_price=float(pos.get("entry_price", 0)),
            mark_price=float(pos.get("mark_price", pos.get("entry_price", 0))),
            unrealized_pnl=pnl,
            last_update=pos.get("last_update", pos.get("opened_at", datetime.now().isoformat()))
        ))
    exposure = _current_exposure()
    realized = getattr(app.state, "realized_pnl", 0.0)
    closed = getattr(app.state, "closed_trades", [])
    stats = calculate_stats(closed)
    return PortfolioState(
        positions=positions,
        trades=app.state.trades[:50],
        closed_trades=closed[:50],
        total_pnl=realized + unrealized,
        realized_pnl=realized,
        unrealized_pnl=unrealized,
        exposure=exposure,
        stats=stats
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
    app.state.closed_trades = []
    app.state.realized_pnl = 0.0
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
        # Get market - try fetching directly first, then search in list
        market = None
        
        # Try to get market by ID directly from Gamma API
        if market_id.isdigit():
            market = app.state.gamma_client.get_market(int(market_id))
        
        # If not found, search in current markets
        if not market:
            markets = app.state.gamma_client.get_current_markets(limit=500)
            for m in markets:
                # Gamma API uses conditionId (camelCase), not condition_id
                if m.get("conditionId") == market_id or str(m.get("id")) == market_id:
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
