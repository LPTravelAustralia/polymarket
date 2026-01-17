#!/usr/bin/env python3
"""
Real-Time News Monitoring Script

Continuously monitors breaking news and trades on Polymarket when
news events are detected that could impact market outcomes.

This script:
1. Monitors NewsAPI for breaking headlines
2. Matches news to active Polymarket markets
3. Uses Claude AI to analyze news impact
4. Generates trading signals
5. Executes trades (if auto_trade enabled)
6. Optional: Validates with Twitter trending data

Usage:
    python scripts/run_news_monitor.py [options]
    
Options:
    --interval SECONDS    Monitoring interval (default: 300)
    --min-liquidity USD   Minimum market liquidity (default: 10000)
    --dry-run            Test mode without real trades
    --use-twitter        Enable Twitter validation
    
Examples:
    # Monitor with 5-minute intervals
    python scripts/run_news_monitor.py --interval 300
    
    # Test mode with Twitter validation
    python scripts/run_news_monitor.py --dry-run --use-twitter
    
    # High-liquidity markets only
    python scripts/run_news_monitor.py --min-liquidity 50000
"""
import sys
import argparse
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
load_dotenv(Path(__file__).parent.parent / ".env")

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.config import load_config
from src.core.client import PolymarketClient
from src.core.market_monitor import MarketMonitor
from src.agents.news_monitor_agent import NewsMonitorAgent
from src.utils.logging_utils import setup_logging


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Real-time news monitoring for Polymarket trading',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        '--interval',
        type=int,
        default=300,
        help='Monitoring interval in seconds (default: 300 = 5 minutes)'
    )
    
    parser.add_argument(
        '--min-liquidity',
        type=float,
        default=10000,
        help='Minimum market liquidity in USD (default: 10000)'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Test mode - generate signals but do not execute trades'
    )
    
    parser.add_argument(
        '--use-twitter',
        action='store_true',
        help='Enable Twitter trending validation'
    )
    
    parser.add_argument(
        '--min-impact',
        type=float,
        default=0.55,
        help='Minimum impact score to generate signal (0-1, default: 0.55)'
    )
    
    parser.add_argument(
        '--min-confidence',
        type=float,
        default=0.50,
        help='Minimum confidence to trade (0-1, default: 0.50)'
    )
    
    parser.add_argument(
        '--once',
        action='store_true',
        help='Run once and exit (no continuous monitoring)'
    )
    
    return parser.parse_args()


def main():
    """Main monitoring loop"""
    args = parse_args()
    
    # Load configuration
    config = load_config()
    
    # Override config with command-line args
    if args.dry_run:
        config.dry_run = True
    
    config.news_monitoring_interval = args.interval
    config.news_min_impact_score = args.min_impact
    config.news_min_confidence = args.min_confidence
    config.news_use_twitter = args.use_twitter
    
    # Setup logging
    logger = setup_logging(config.log_level)
    
    logger.info("=" * 80)
    logger.info("POLYMARKET NEWS MONITORING BOT")
    logger.info("=" * 80)
    logger.info(f"Mode: {'DRY RUN' if config.dry_run else 'LIVE TRADING'}")
    logger.info(f"Monitoring Interval: {args.interval}s")
    logger.info(f"Min Liquidity: ${args.min_liquidity:,.0f}")
    logger.info(f"Min Impact Score: {args.min_impact:.2f}")
    logger.info(f"Min Confidence: {args.min_confidence:.2f}")
    logger.info(f"Twitter Validation: {'ENABLED' if args.use_twitter else 'DISABLED'}")
    logger.info("=" * 80)
    
    # Check API keys
    if not config.anthropic_api_key:
        logger.warning("⚠️  ANTHROPIC_API_KEY not set - AI analysis will be limited")
    
    from src.connectors.news import NewsConnector
    news_connector = NewsConnector()
    if not news_connector.api_key:
        logger.error("❌ NEWSAPI_KEY not set - cannot fetch news")
        logger.error("Get your free API key at: https://newsapi.org/register")
        return 1
    
    if args.use_twitter:
        from src.connectors.twitter import TwitterConnector
        twitter_connector = TwitterConnector()
        if not twitter_connector.bearer_token:
            logger.warning("⚠️  TWITTER_BEARER_TOKEN not set - Twitter validation disabled")
            args.use_twitter = False
    
    # Initialize components
    try:
        # Initialize client (will use REST API in dry-run mode)
        client = PolymarketClient(config)
        market_monitor = MarketMonitor(client, config)
        
        agent = NewsMonitorAgent(config)
        agent.market_monitor = market_monitor
        
        logger.info("✅ All components initialized successfully")
        
    except Exception as e:
        logger.error(f"❌ Failed to initialize: {e}")
        return 1
    
    # Run monitoring
    try:
        if args.once:
            # Single run mode
            logger.info("\n🔍 Running single news check...")
            
            # Get active markets
            markets = market_monitor.discover_markets(min_liquidity=args.min_liquidity)
            logger.info(f"Found {len(markets)} markets with sufficient liquidity")
            
            # Generate signals
            signals = agent.generate_signals(markets)
            
            if signals:
                logger.info(f"\n📊 Generated {len(signals)} trading signals:\n")
                
                for i, signal in enumerate(signals, 1):
                    logger.info(f"{i}. {signal.market_question[:70]}")
                    logger.info(f"   📰 News: {signal.news_headline[:80]}")
                    logger.info(f"   📈 Direction: {signal.direction}")
                    logger.info(f"   💯 Confidence: {signal.confidence:.2%}")
                    logger.info(f"   ⚡ Impact: {signal.impact_score:.2f}")
                    logger.info(f"   ⏱️  Urgency: {signal.urgency:.2f}")
                    logger.info(f"   🔍 Source: {signal.news_source}")
                    logger.info(f"   💭 Reasoning: {signal.reasoning}")
                    logger.info("")
            else:
                logger.info("No trading signals generated")
            
        else:
            # Continuous monitoring mode
            logger.info("\n🚀 Starting continuous monitoring...\n")
            agent.monitor_loop(min_liquidity=args.min_liquidity)
        
        return 0
        
    except KeyboardInterrupt:
        logger.info("\n\n👋 Monitoring stopped by user")
        return 0
        
    except Exception as e:
        logger.error(f"\n❌ Error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
