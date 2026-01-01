"""
Market discovery and monitoring module
"""
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

from src.core.client import PolymarketClient
from src.core.config import Config

logger = logging.getLogger(__name__)


class MarketMonitor:
    """
    Monitor and discover markets on Polymarket
    """
    
    def __init__(self, client: PolymarketClient, config: Config):
        """
        Initialize market monitor
        
        Args:
            client: Polymarket client instance
            config: Configuration object
        """
        self.client = client
        self.config = config
        self.tracked_markets: Dict[str, Dict[str, Any]] = {}
    
    def discover_markets(
        self,
        min_liquidity: Optional[float] = None,
        tags: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Discover active markets based on criteria
        
        Args:
            min_liquidity: Minimum liquidity requirement
            tags: Filter by specific tags
            
        Returns:
            List of markets matching criteria
        """
        min_liq = min_liquidity or self.config.min_liquidity
        
        markets = self.client.get_markets()
        filtered_markets = []
        
        for market in markets:
            # Check liquidity
            liquidity = float(market.get("liquidity", 0) or 0)
            if liquidity < min_liq:
                continue
            
            # Check tags if specified
            if tags:
                market_tags = market.get("tags", [])
                if not any(tag in market_tags for tag in tags):
                    continue
            
            # Check if market is still active
            end_date = market.get("end_date")
            if end_date:
                try:
                    if datetime.fromisoformat(end_date.replace('Z', '+00:00')) < datetime.now():
                        continue
                except (ValueError, TypeError):
                    pass  # Skip date check if parsing fails
            
            filtered_markets.append(market)
        
        logger.info(f"Discovered {len(filtered_markets)} markets matching criteria")
        return filtered_markets
    
    def get_market_prices(self, condition_id: str) -> Dict[str, float]:
        """
        Get current prices for a market
        
        Args:
            condition_id: Market condition ID
            
        Returns:
            Dictionary of token_id to price
        """
        market = self.client.get_market(condition_id)
        if not market:
            return {}
        
        prices = {}
        for token in market.get("tokens", []):
            token_id = token.get("token_id")
            orderbook = self.client.get_orderbook(token_id)
            
            # Get best bid and ask
            bids = orderbook.get("bids", [])
            asks = orderbook.get("asks", [])
            
            best_bid = float(bids[0]["price"]) if bids else 0.0
            best_ask = float(asks[0]["price"]) if asks else 1.0
            
            mid_price = (best_bid + best_ask) / 2
            prices[token_id] = mid_price
        
        return prices
    
    def analyze_market_depth(self, token_id: str) -> Dict[str, Any]:
        """
        Analyze orderbook depth for a token
        
        Args:
            token_id: Token ID
            
        Returns:
            Analysis of market depth
        """
        orderbook = self.client.get_orderbook(token_id)
        
        bids = orderbook.get("bids", [])
        asks = orderbook.get("asks", [])
        
        total_bid_volume = sum(float(bid.get("size", 0)) for bid in bids)
        total_ask_volume = sum(float(ask.get("size", 0)) for ask in asks)
        
        best_bid = float(bids[0]["price"]) if bids else 0.0
        best_ask = float(asks[0]["price"]) if asks else 1.0
        spread = best_ask - best_bid
        
        return {
            "token_id": token_id,
            "best_bid": best_bid,
            "best_ask": best_ask,
            "spread": spread,
            "spread_percentage": (spread / best_ask * 100) if best_ask > 0 else 0,
            "total_bid_volume": total_bid_volume,
            "total_ask_volume": total_ask_volume,
            "bid_ask_ratio": total_bid_volume / total_ask_volume if total_ask_volume > 0 else 0
        }
    
    def track_market(self, condition_id: str):
        """
        Start tracking a specific market
        
        Args:
            condition_id: Market condition ID
        """
        market = self.client.get_market(condition_id)
        if market:
            self.tracked_markets[condition_id] = market
            logger.info(f"Now tracking market: {market.get('question', condition_id)}")
    
    def get_tracked_markets(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all tracked markets
        
        Returns:
            Dictionary of tracked markets
        """
        return self.tracked_markets
    
    def find_arbitrage_opportunities(self) -> List[Dict[str, Any]]:
        """
        Find potential arbitrage opportunities
        
        Returns:
            List of arbitrage opportunities
        """
        opportunities = []
        
        for condition_id, market in self.tracked_markets.items():
            tokens = market.get("tokens", [])
            
            # For binary markets, check if prices don't sum to 1
            if len(tokens) == 2:
                prices = self.get_market_prices(condition_id)
                total_price = sum(prices.values())
                
                if total_price < 0.95 or total_price > 1.05:
                    opportunities.append({
                        "condition_id": condition_id,
                        "question": market.get("question"),
                        "total_price": total_price,
                        "type": "binary_arbitrage"
                    })
        
        return opportunities
