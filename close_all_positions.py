#!/usr/bin/env python3
"""
Close all open positions immediately for a clean test slate
"""
import httpx
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)-8s | %(message)s')
logger = logging.getLogger(__name__)

BACKEND_URL = "http://localhost:8000"

def close_all_positions():
    """Close all open positions"""
    logger.info("=" * 70)
    logger.info("CLOSING ALL OPEN POSITIONS")
    logger.info("=" * 70)
    
    # Get current positions
    resp = httpx.get(f"{BACKEND_URL}/api/bot/portfolio", timeout=30)
    portfolio = resp.json()
    positions = portfolio.get('positions', [])
    
    logger.info(f"Found {len(positions)} open positions\n")
    
    closed_count = 0
    total_pnl = 0.0
    
    for pos in positions:
        market_id = pos.get('market_id')
        question = pos.get('question', '')[:50]
        side = pos.get('side', '?')
        pnl = pos.get('unrealized_pnl', 0)
        
        logger.info(f"Closing: {side.upper()} ${pos.get('size', 0)} | {question}...")
        
        try:
            resp = httpx.post(
                f"{BACKEND_URL}/api/bot/close-position",
                json={"market_id": market_id, "reason": "FULL_RESET"},
                timeout=30
            )
            
            if resp.status_code == 200:
                data = resp.json()
                if data.get('success'):
                    trade = data.get('trade', {})
                    realized_pnl = trade.get('pnl', 0)
                    closed_count += 1
                    total_pnl += realized_pnl
                    logger.info(f"  ✓ Closed with PnL: ${realized_pnl:+.2f}")
                else:
                    logger.info(f"  ✗ Failed: {data.get('detail', 'Unknown error')}")
            else:
                logger.info(f"  ✗ HTTP {resp.status_code}")
        except Exception as e:
            logger.error(f"  ✗ Error: {e}")
    
    logger.info(f"\n" + "=" * 70)
    logger.info(f"RESULTS:")
    logger.info(f"  Positions closed: {closed_count}/{len(positions)}")
    logger.info(f"  Total realized PnL: ${total_pnl:+.2f}")
    logger.info("=" * 70)
    
    return closed_count

if __name__ == "__main__":
    close_all_positions()
