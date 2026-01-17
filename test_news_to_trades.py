#!/usr/bin/env python3
"""
End-to-End Test: News → Analysis → Signals → Trade Execution

This test verifies the complete pipeline works:
1. Create synthetic news article
2. Match to a market
3. Analyze impact via backend
4. Generate trading signal
5. Execute trade (dry-run)
"""
import sys
import logging
from pathlib import Path

# Setup path
sys.path.insert(0, str(Path(__file__).parent))

from src.agents.news_monitor_agent import NewsMonitorAgent, NewsSignal
from src.connectors.news import Article
from src.core.config import Config

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s | %(levelname)-8s | %(name)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_end_to_end():
    """Run end-to-end news→trade pipeline test"""
    logger.info("=" * 80)
    logger.info("END-TO-END NEWS TRADING PIPELINE TEST")
    logger.info("=" * 80)
    
    # Initialize agent
    config = Config()
    agent = NewsMonitorAgent(config)
    logger.info(f"✓ Agent initialized (backend: {agent.backend_url})")
    
    # Fetch markets
    markets = agent.market_monitor.discover_markets(min_liquidity=10000)
    logger.info(f"✓ Loaded {len(markets)} markets")
    
    # Find a Fed-related market
    fed_markets = [m for m in markets if 'fed' in m.get('question', '').lower()]
    if not fed_markets:
        logger.error("❌ No Fed-related markets found")
        return False
    
    fed_market = fed_markets[0]
    logger.info(f"✓ Testing with market: {fed_market['question'][:80]}")
    
    # Create synthetic, highly relevant news
    article = Article(
        title="BREAKING: Federal Reserve Announces 0.25% Interest Rate Increase",
        description="The Federal Reserve's policy committee has voted unanimously to raise the benchmark interest rate by 25 basis points, citing ongoing inflation concerns.",
        url="https://example.com/fed-rate-increase",
        source="Federal Reserve Press Release",
        published_at="2026-01-17T14:30:00Z"
    )
    logger.info(f"✓ Created synthetic article: '{article.title}'")
    
    # Analyze impact
    impact, direction, confidence, reasoning = agent._analyze_news_impact(
        article,
        fed_market['question'],
        ['fed', 'rate', 'increase']
    )
    logger.info(f"✓ Analysis complete:")
    logger.info(f"  - Impact: {impact:.2f}")
    logger.info(f"  - Direction: {direction}")
    logger.info(f"  - Confidence: {confidence:.2f}")
    logger.info(f"  - Reasoning: {reasoning[:100]}")
    
    # Check if signal would be generated
    min_impact = config.news_min_impact_score
    min_confidence = config.news_min_confidence
    
    logger.info(f"\nThreshold Check:")
    logger.info(f"  - Min Impact: {min_impact:.2f} (article: {impact:.2f}) {'✓' if impact >= min_impact else '❌'}")
    logger.info(f"  - Min Confidence: {min_confidence:.2f} (article: {confidence:.2f}) {'✓' if confidence >= min_confidence else '❌'}")
    
    if impact >= min_impact and confidence >= min_confidence:
        logger.info(f"\n✓ SIGNAL GENERATED - Would execute trade!")
        
        # Create signal
        signal = NewsSignal(
            market_id=fed_market.get('id'),
            market_question=fed_market['question'],
            news_headline=article.title,
            news_source=article.source,
            published_at=article.published_at,
            impact_score=impact,
            direction=direction,
            confidence=confidence,
            urgency=0.8,
            reasoning=reasoning,
            keywords_matched=['fed', 'rate', 'increase']
        )
        
        # Execute trade (dry-run)
        logger.info(f"\n🚀 EXECUTING TRADE:")
        logger.info(f"  Market: {signal.market_question}")
        logger.info(f"  Direction: {signal.direction}")
        logger.info(f"  Confidence: {signal.confidence:.1%}")
        logger.info(f"  Mode: {'DRY RUN' if config.dry_run else 'LIVE'}")
        
        agent._execute_news_trade(signal)
        return True
    else:
        logger.warning(f"\n❌ SIGNAL FILTERED OUT - Below thresholds")
        logger.warning(f"Need to either:")
        logger.warning(f"  1. Lower thresholds (impact {min_impact} → 0.10, confidence {min_confidence} → 0.20)")
        logger.warning(f"  2. Use news with higher impact scores")
        return False

if __name__ == "__main__":
    success = test_end_to_end()
    sys.exit(0 if success else 1)
