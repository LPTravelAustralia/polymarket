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

# Backend running locally on VM
BACKEND_URL = "http://localhost:8000"
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
            # Use richer keywords for better analysis
            if not keywords or keywords == ['news']:
                keywords = ['fed', 'interest', 'rates', 'trump', 'election', 'bitcoin', 'nba', 'ukraine']
            
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
        markets = self.get_markets(limit=200)
        if not markets:
            logger.error("No markets available")
            return
        
        # Select diverse test markets - test MORE markets for better coverage
        test_markets = []
        categories = {
            'fed': lambda q: 'fed' in q.lower() and 'interest' in q.lower(),
            'sports': lambda q: any(w in q.lower() for w in ['nba', 'nfl', 'championship', 'super bowl', 'win', 'playoff']),
            'politics': lambda q: any(w in q.lower() for w in ['trump', 'election', 'president', 'democrat', 'republican']),
            'crypto': lambda q: any(w in q.lower() for w in ['bitcoin', 'btc', 'crypto', 'eth', 'crypto']),
            'world': lambda q: any(w in q.lower() for w in ['ukraine', 'russia', 'china', 'war', 'ceasefire', 'conflict'])
        }
        
        # Get up to 3 markets per category instead of just 1
        for cat, matcher in categories.items():
            matches = [m for m in markets if matcher(m.get('question', ''))][:3]
            for match in matches:
                test_markets.append({'category': cat, 'market': match})
        
        # Limit total to avoid too long runs, but test many more
        test_markets = test_markets[:12]
        
        if not test_markets:
            logger.warning("No suitable test markets found")
            return
        
        logger.info(f"\n📊 Testing {len(test_markets)} markets across {len(categories)} categories:")
        for tm in test_markets:
            logger.info(f"  - {tm['category'].upper()}: {tm['market']['question'][:60]}")
        
        # Define market-specific keywords for targeted searches
        market_keywords = {
            'fed': ['federal reserve', 'fed meeting', 'interest rates', 'jerome powell'],
            'sports': ['nba', 'nfl', 'super bowl', 'championship', 'playoffs'],
            'politics': ['trump', 'election', 'biden', 'congress', 'senate'],
            'crypto': ['bitcoin', 'ethereum', 'crypto', 'blockchain'],
            'world': ['ukraine', 'russia', 'china', 'international']
        }
        
        logger.info(f"\n🔍 Analyzing news against test markets (market-specific keywords)...")
        
        signals_generated = 0
        trades_executed = 0
        
        # Analyze each market with its own relevant articles
        for tm in test_markets:
            market = tm['market']
            cat = tm['category']
            logger.info(f"\n  📊 {cat.upper()}: {market['question'][:55]}")
            
            # Get articles relevant to this market category
            keywords_for_market = market_keywords.get(cat, [cat])
            articles_for_market = []
            
            # Search more aggressively - 3 keywords per market, 4 articles each
            for keyword in keywords_for_market[:3]:
                articles = self.search_news(keyword, limit=4)
                articles_for_market.extend(articles)
            
            # Remove duplicates
            seen_urls = set()
            unique_market_articles = []
            for a in articles_for_market:
                url = a.get('url', a.get('title', ''))
                if url not in seen_urls:
                    seen_urls.add(url)
                    unique_market_articles.append(a)
            
            logger.info(f"    {len(unique_market_articles)} articles")
            
            # Analyze up to 4 articles (more chances for signal)
            for i, article in enumerate(unique_market_articles[:4]):
                headline = article.get('title', '')
                description = article.get('description', '')
                source = article.get('source', 'Unknown')
                
                logger.info(f"    [{i+1}] {headline[:45]}...")
                
                analysis = self.analyze_news(
                    headline=headline,
                    description=description,
                    source=source,
                    market_question=market['question'],
                    keywords=[cat, 'news']
                )
                
                if analysis:
                    impact = analysis.get('impact_score', 0)
                    direction = analysis.get('direction', 'NEUTRAL')
                    confidence = analysis.get('confidence', 0)
                    
                    logger.info(f"        Impact: {impact:.2f} | Dir: {direction} | Conf: {confidence:.2f}")
                    
                    # Check thresholds (0.15 and 0.30)
                    if impact >= 0.15 and confidence >= 0.30 and direction != 'NEUTRAL':
                        logger.info(f"        ✓ SIGNAL! Placing trade...")
                        signals_generated += 1
                        side = 'yes' if direction.upper() == 'YES' else 'no'
                        trade = self.quick_trade(market['id'], side=side, size=25.0)
                        if trade and trade.get('success'):
                            trades_executed += 1
                            t = trade.get('trade', {})
                            logger.info(f"        🟢 OPENED: {t.get('side','?').upper()} ${t.get('size',0)}")
                            break  # One trade per market max
                        else:
                            logger.info(f"        ✗ Rejected (likely existing position)")
                    else:
                        logger.info(f"        ✗ Below threshold")
        
        # Summary
        logger.info(f"\n" + "=" * 80)
        logger.info(f"RESULTS:")
        logger.info(f"  Markets tested: {len(test_markets)}")
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
