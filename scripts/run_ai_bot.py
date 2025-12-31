#!/usr/bin/env python3
"""
AI-powered prediction bot example
"""
import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.config import load_config
from src.agents.ai_agent import AIAgent
from src.utils.logging_utils import setup_logging


def main():
    """Run AI prediction bot"""
    # Load configuration
    config = load_config()
    
    # Setup logging
    logger = setup_logging(config.log_level)
    logger.info("Starting AI Prediction Bot")
    
    # Check AI is enabled
    if not config.use_ai_predictions:
        logger.warning("AI predictions are disabled in config. Enable USE_AI_PREDICTIONS=true")
        return
    
    if not config.openai_api_key and not config.anthropic_api_key:
        logger.error("No AI API key configured. Set OPENAI_API_KEY or ANTHROPIC_API_KEY")
        return
    
    # Initialize agent
    agent = AIAgent(config)
    
    try:
        # Run trading loop
        while True:
            logger.info("Running AI prediction cycle...")
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
