#!/usr/bin/env python3
"""
Quick Position Closer - Auto-close paper positions after time threshold
Simulates rapid trading cycles for testing win rate and realized PnL
"""
import httpx
import time
from datetime import datetime, timedelta
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)-8s | %(message)s')
logger = logging.getLogger(__name__)

BACKEND_URL = "http://localhost:8000"
TIMEOUT = 30.0

def get_open_positions():
    """Fetch current open positions"""
    try:
        resp = httpx.get(f"{BACKEND_URL}/api/bot/portfolio", timeout=TIMEOUT)
        if resp.status_code == 200:
            portfolio = resp.json()
            # API returns 'positions' (current snapshots) not 'open_trades'
            return portfolio.get('positions', [])
    except Exception as e:
        logger.error(f"Failed to get positions: {e}")
    return []

def close_position(market_id: str, reason: str = "AUTO"):
    """Close a position"""
    try:
        resp = httpx.post(
            f"{BACKEND_URL}/api/bot/close-position",
            json={"market_id": market_id, "reason": reason},
            timeout=TIMEOUT
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get('success'):
                trade = data.get('trade', {})
                pnl = trade.get('pnl', 0)
                return True, pnl
            else:
                return False, 0
    except Exception as e:
        logger.error(f"Failed to close {market_id}: {e}")
    return False, 0

def auto_close_old_positions(age_minutes: int = 3):
    """Close positions older than N minutes"""
    logger.info(f"Checking for positions older than {age_minutes} minutes...")
    
    positions = get_open_positions()
    if not positions:
        logger.info("No open positions")
        return 0, 0.0
    
    logger.info(f"Found {len(positions)} open positions")
    
    now = datetime.now()
    cutoff = now - timedelta(minutes=age_minutes)
    closed_count = 0
    total_pnl = 0.0
    
    for pos in positions:
        # Use 'last_update' field (not 'timestamp' which is in trades)
        opened_str = pos.get('last_update', pos.get('timestamp', ''))
        if not opened_str:
            continue
        
        try:
            opened = datetime.fromisoformat(opened_str.replace('Z', '+00:00'))
            opened = opened.replace(tzinfo=None)  # Strip TZ for comparison
        except:
            logger.debug(f"Could not parse timestamp: {opened_str}")
            continue
        
        age = now - opened
        if age.total_seconds() >= age_minutes * 60:
            market_id = pos.get('market_id')
            question = pos.get('question', '')[:50]
            logger.info(f"  Closing position (age: {age.total_seconds()/60:.1f}m): {question}...")
            
            success, pnl = close_position(market_id, reason="AUTO_AGED")
            if success:
                closed_count += 1
                total_pnl += pnl
                logger.info(f"    ✓ Closed with PnL: ${pnl:+.2f}")
            else:
                logger.info(f"    ✗ Failed to close")
    
    return closed_count, total_pnl

if __name__ == "__main__":
    logger.info("=" * 80)
    logger.info("QUICK POSITION CLOSER")
    logger.info("=" * 80)
    
    closed, pnl = auto_close_old_positions(age_minutes=3)
    
    logger.info(f"\n" + "=" * 80)
    logger.info(f"RESULTS:")
    logger.info(f"  Positions closed: {closed}")
    logger.info(f"  Total PnL: ${pnl:+.2f}")
    logger.info("=" * 80)
