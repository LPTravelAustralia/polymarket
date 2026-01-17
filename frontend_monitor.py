#!/usr/bin/env python3
"""
Frontend News Monitor - Calls the actual GCloud backend API
Simulates the full news trading pipeline by hitting backend endpoints
"""
import httpx
import json
import logging
from typing import List, Dict, Optional
from datetime import datetime, timezone

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s'
)
logger = logging.getLogger(__name__)

# Backend running on GCloud VM
BACKEND_URL = "http://34.29.163.176:8000"
TIMEOUT = 30.0

class FrontendMonitor:
    def __init__(self):
        self.http = httpx.Client(timeout=TIMEOUT)
        logger.info(f"Initialized frontend monitor (backend: {BACKEND_URL})")
    
    def check_backend(self) -> bool:
        """Check if backend is healthy"""
        try:
            resp = self.http.get(f"{BACKEND_URL}/api/health")
            data = resp.json()
            logger.info(f"✓ Backend healthy: anthropic={data.get('anthropic_key')}, newsapi={data.get('newsapi_key')}")
            return True
        except Exception as e:
            logger.error(f"❌ Backend unreachable: {e}")
            return False
    
    def get_markets(self, limit: int = 100) -> List[Dict]:
        """Fetch markets from backend"""
        try:
            resp = self.http.get(f"{BACKEND_URL}/api/markets", params={"limit": limit})
            markets = resp.json().get("markets", [])
            logger.info(f"✓ Fetched {len(markets)} markets")
            return markets
        except Exception as e:
            logger.error(f"❌ Failed to fetch markets: {e}")
            return []
    
    def search_news(self, query: str, limit: int = 15) -> List[Dict]:
        """Search for news articles"""
        try:
            resp = self.http.get(
                f"{BACKEND_URL}/api/news",
                params={"query": query, "limit": limit}
            )
            articles = resp.json().get("articles", [])
            logger.info(f"  Found {len(articles)} articles for '{query}'")
            return articles
        except Exception as e:
            logger.error(f"  Error searching '{query}': {e}")
            return []
    
    def analyze_news(self, headline: str, description: str, source: str, 
                     market_question: str, keywords: List[str]) -> Optional[Dict]:
        """Analyze news impact via backend"""
        try:
            payload = {
                "headline": headline,
                "description": description,
                "source": source,
                "market_question": market_question,
                "keywords": keywords
            }
            resp = self.http.post(
                f"{BACKEND_URL}/api/news/analyze",
                json=payload
            )
            if resp.status_code == 200:
                return resp.json()
            else:
                logger.debug(f"  Analysis error: {resp.status_code}")
                return None
        except Exception as e:
            logger.debug(f"  Analysis failed: {e}")
            return None

    def quick_trade(self, market_id: str, side: str, size: float = 25.0) -> Optional[Dict]:
        """Open a paper trade via backend quick-trade endpoint"""
        try:
            payload = {"market_id": market_id, "side": side.lower(), "size": size}
            resp = self.http.post(f"{BACKEND_URL}/api/bot/quick-trade", json=payload)
            if resp.status_code == 200:
                return resp.json()
            else:
                logger.info(f"      Trade rejected: {resp.status_code} {resp.text[:120]}")
                return None
        except Exception as e:
            logger.info(f"      Trade failed: {e}")
            return None

    def get_portfolio(self) -> Optional[Dict]:
        try:
            resp = self.http.get(f"{BACKEND_URL}/api/bot/portfolio")
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return None
    
    def run_pipeline(self):
        """Run full news → analysis → signals pipeline"""
        logger.info("=" * 80)
        logger.info("FRONTEND NEWS MONITOR - Using Actual GCloud Backend")
        logger.info("=" * 80)
        session_start = datetime.now(timezone.utc).isoformat()
        
        # Check backend
        if not self.check_backend():
            logger.error("Cannot proceed without backend")
            return
        
        # Get markets
        markets = self.get_markets(limit=50)
        if not markets:
            logger.error("No markets available")
            return
        
        logger.info(f"\n📊 Searching for news about key topics...")
        
        # Search for relevant news
        all_articles = []
        keywords = ['fed', 'trump', 'election', 'interest', 'ukraine']
        
        for keyword in keywords:
            articles = self.search_news(keyword, limit=10)
            all_articles.extend(articles)
        
        # Remove duplicates
        seen_urls = set()
        unique_articles = []
        for a in all_articles:
            url = a.get('url', a.get('title', ''))
            if url not in seen_urls:
                seen_urls.add(url)
                unique_articles.append(a)
        
        logger.info(f"\n✓ Total unique articles: {len(unique_articles)}")
        
        # Analyze top articles against Fed market
        logger.info(f"\n🔍 Analyzing news impact...")
        
        fed_market = next((m for m in markets if 'fed' in m.get('question', '').lower()), None)
        if not fed_market:
            logger.warning("No Fed market found")
            return
        
        logger.info(f"Testing market: {fed_market.get('question', '')[:70]}")
        
        signals_generated = 0
        trades_executed = 0
        
        # Analyze first 5 articles
        for i, article in enumerate(unique_articles[:5]):
            headline = article.get('title', '')
            description = article.get('description', '')
            source = article.get('source', 'Unknown')
            
            logger.info(f"\n  [{i+1}/5] Analyzing: {headline[:60]}...")
            
            analysis = self.analyze_news(
                headline=headline,
                description=description,
                source=source,
                market_question=fed_market['question'],
                keywords=['fed', 'rate', 'interest']
            )
            
            if analysis:
                impact = analysis.get('impact_score', 0)
                direction = analysis.get('direction', 'NEUTRAL')
                confidence = analysis.get('confidence', 0)
                
                logger.info(f"      Impact: {impact:.2f} | Direction: {direction} | Confidence: {confidence:.2f}")
                
                # Check thresholds (0.15 and 0.30)
                if impact >= 0.15 and confidence >= 0.30 and direction != 'NEUTRAL':
                    logger.info(f"      ✓ SIGNAL GENERATED! Placing paper trade...")
                    signals_generated += 1
                    side = 'yes' if direction.upper() == 'YES' else 'no'
                    trade = self.quick_trade(fed_market['id'], side=side, size=25.0)
                    if trade and trade.get('success'):
                        trades_executed += 1
                        t = trade.get('trade', {})
                        logger.info(f"      🟢 TRADE OPENED: {t.get('side','?').upper()} ${t.get('size',0)} at {t.get('entry_price','?')}")
                    else:
                        logger.info(f"      ✗ Trade not opened")
                else:
                    logger.info(f"      ✗ Below threshold (need impact≥0.15, conf≥0.30)")
        
        # Summary
        logger.info(f"\n" + "=" * 80)
        logger.info(f"RESULTS:")
        logger.info(f"  Articles analyzed: {min(5, len(unique_articles))}")
        logger.info(f"  Signals generated: {signals_generated}")
        logger.info(f"  Trades executed: {trades_executed}")
        
        # Show fresh portfolio snapshot
        portfolio = self.get_portfolio()
        if portfolio:
            stats = portfolio.get('stats', {})
            logger.info(f"\n📊 Fresh Portfolio Snapshot:")
            logger.info(f"  Total PnL: {portfolio.get('total_pnl')}")
            logger.info(f"  Realized PnL: {portfolio.get('realized_pnl')}")
            logger.info(f"  Open Positions: {stats.get('active_positions')} | Win Rate: {stats.get('win_rate')}% | Total Trades: {stats.get('total_trades')}")
        else:
            logger.info("\n📊 Portfolio snapshot unavailable")

        # Query session-only stats since we started
        try:
            resp = self.http.get(f"{BACKEND_URL}/api/stats/since", params={"since": session_start})
            if resp.status_code == 200:
                fresh = resp.json()
                logger.info("\n🆕 Session Stats (fresh since run start):")
                logger.info(f"  Trades opened: {fresh['counts']['trades_opened']}")
                logger.info(f"  Trades closed: {fresh['counts']['trades_closed']}")
                logger.info(f"  Realized PnL: {fresh['pnl']['realized']}")
                logger.info(f"  Win rate: {fresh['stats']['win_rate']}% | PF: {fresh['stats']['profit_factor']}")
            else:
                logger.info(f"\nSession stats unavailable: {resp.status_code}")
        except Exception as e:
            logger.info(f"\nSession stats error: {e}")
        logger.info(f"=" * 80)

if __name__ == "__main__":
    monitor = FrontendMonitor()
    monitor.run_pipeline()
