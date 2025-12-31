#!/usr/bin/env python3
"""
Arbitrage bot example
"""
import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.config import load_config
from src.agents.arbitrage_agent import ArbitrageAgent
from src.utils.logging_utils import setup_logging


def main():
    """Run arbitrage bot"""
    # Load configuration
    config = load_config()
    
    # Setup logging
    logger = setup_logging(config.log_level)
    logger.info("Starting Arbitrage Bot")
    
    # Initialize agent
    agent = ArbitrageAgent(config)
    
    try:
        # Run trading loop
        while True:
            logger.info("Scanning for arbitrage opportunities...")
            
            # Discover markets
            markets = agent.monitor.discover_markets()
            
            opportunities_found = 0
            
            for market in markets:
                # Analyze for arbitrage
                analysis = agent.analyze_market(market)
                
                if analysis.get("has_arbitrage"):
                    opportunities_found += 1
                    margin = analysis.get("arbitrage_margin", 0)
                    logger.info(f"Found arbitrage: {market.get('question')}")
                    logger.info(f"  Margin: {margin * 100:.2f}%")
                    
                    # Execute if auto-trading is enabled
                    if config.auto_trade:
                        logger.info("  Executing arbitrage...")
                        results = agent.execute_arbitrage(analysis)
                        logger.info(f"  Executed {len(results)} trades")
            
            logger.info(f"Found {opportunities_found} arbitrage opportunities")
            
            # Display performance
            stats = agent.get_performance_stats()
            logger.info(f"Performance: {stats}")
            
            # Wait before next cycle
            logger.info(f"Waiting {config.monitoring_interval} seconds...")
            time.sleep(config.monitoring_interval)
    
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot error: {e}")
        raise


if __name__ == "__main__":
    main()
