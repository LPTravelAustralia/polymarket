#!/usr/bin/env python3
"""
Simple trading bot example
"""
import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.config import load_config
from src.agents.momentum_agent import MomentumAgent
from src.utils.logging_utils import setup_logging


def main():
    """Run simple trading bot"""
    # Load configuration
    config = load_config()
    
    # Setup logging
    logger = setup_logging(config.log_level)
    logger.info("Starting Polymarket Trading Bot")
    
    # Initialize agent
    agent = MomentumAgent(config)
    
    try:
        # Run trading loop
        while True:
            logger.info("Running trading cycle...")
            agent.run()
            
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
