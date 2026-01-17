#!/usr/bin/env python3
"""
Market monitoring example
"""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.config import load_config
from src.core.client import PolymarketClient
from src.core.market_monitor import MarketMonitor
from src.utils.logging_utils import setup_logging


def main():
    """Monitor markets and display information"""
    # Load configuration
    config = load_config()
    
    # Setup logging
    logger = setup_logging(config.log_level)
    logger.info("Starting Market Monitor")
    
    # Initialize client and monitor
    client = PolymarketClient(config)
    monitor = MarketMonitor(client, config)
    
    # Discover markets
    logger.info("Discovering markets...")
    markets = monitor.discover_markets(min_liquidity=1000)
    
    logger.info(f"Found {len(markets)} markets with sufficient liquidity")
    
    # Display top markets
    for i, market in enumerate(markets[:10], 1):
        logger.info(f"\n{i}. {market.get('question')}")
        logger.info(f"   Liquidity: ${market.get('liquidity', 0):,.2f}")
        logger.info(f"   Volume: ${market.get('volume', 0):,.2f}")
        
        # Get prices
        condition_id = market.get("condition_id")
        prices = monitor.get_market_prices(condition_id)
        
        for token_id, price in prices.items():
            logger.info(f"   Token {token_id}: {price:.3f}")
    
    # Check for arbitrage
    logger.info("\nChecking for arbitrage opportunities...")
    for market in markets[:20]:
        monitor.track_market(market.get("condition_id"))
    
    opportunities = monitor.find_arbitrage_opportunities()
    
    if opportunities:
        logger.info(f"Found {len(opportunities)} arbitrage opportunities:")
        for opp in opportunities:
            logger.info(f"  - {opp['question']}: Total price = {opp['total_price']:.3f}")
    else:
        logger.info("No arbitrage opportunities found")


if __name__ == "__main__":
    main()
