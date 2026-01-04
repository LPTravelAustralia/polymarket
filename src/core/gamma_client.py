"""
Gamma API client for market discovery and metadata
Based on official Polymarket agents framework
"""
import logging
from typing import Dict, List, Optional, Any
import httpx

from src.core.config import Config

logger = logging.getLogger(__name__)


class GammaMarketClient:
    """
    Client for Polymarket Gamma API - handles market discovery and metadata
    Separate from CLOB API which handles order execution
    """
    
    def __init__(self, config: Optional[Config] = None):
        """Initialize Gamma client"""
        self.gamma_url = "https://gamma-api.polymarket.com"
        self.gamma_markets_endpoint = f"{self.gamma_url}/markets"
        self.gamma_events_endpoint = f"{self.gamma_url}/events"
        self.config = config
        
    def get_markets(
        self,
        querystring_params: Optional[Dict] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get markets from Gamma API with optional filters
        
        Args:
            querystring_params: Query parameters for filtering
            limit: Maximum number of markets to return
            
        Returns:
            List of market data dictionaries
        """
        try:
            params = querystring_params or {}
            if "limit" not in params:
                params["limit"] = limit
                
            response = httpx.get(self.gamma_markets_endpoint, params=params, timeout=30)
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Gamma API error: {response.status_code}")
                return []
        except Exception as e:
            logger.error(f"Error fetching markets from Gamma: {e}")
            return []
    
    def get_events(
        self,
        querystring_params: Optional[Dict] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get events from Gamma API with optional filters
        
        Args:
            querystring_params: Query parameters for filtering
            limit: Maximum number of events to return
            
        Returns:
            List of event data dictionaries
        """
        try:
            params = querystring_params or {}
            if "limit" not in params:
                params["limit"] = limit
                
            response = httpx.get(self.gamma_events_endpoint, params=params, timeout=30)
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Gamma API error: {response.status_code}")
                return []
        except Exception as e:
            logger.error(f"Error fetching events from Gamma: {e}")
            return []
    
    def get_current_markets(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get active, non-closed, non-archived markets"""
        return self.get_markets(
            querystring_params={
                "active": True,
                "closed": False,
                "archived": False,
                "limit": limit,
            }
        )
    
    def get_all_current_markets(self, max_markets: int = 5000) -> List[Dict[str, Any]]:
        """
        Get ALL active markets using pagination.
        The Gamma API has a max limit of 500 per request, so we paginate.
        
        Args:
            max_markets: Maximum total markets to fetch (default 5000 to be reasonable)
            
        Returns:
            List of all active market data dictionaries
        """
        all_markets = []
        offset = 0
        page_size = 500  # API max
        
        while len(all_markets) < max_markets:
            try:
                params = {
                    "active": True,
                    "closed": False,
                    "archived": False,
                    "limit": page_size,
                    "offset": offset,
                }
                response = httpx.get(self.gamma_markets_endpoint, params=params, timeout=30)
                if response.status_code != 200:
                    logger.error(f"Gamma API error: {response.status_code}")
                    break
                    
                batch = response.json()
                if not batch:
                    break  # No more markets
                    
                all_markets.extend(batch)
                logger.info(f"Fetched {len(all_markets)} markets (offset {offset})")
                
                if len(batch) < page_size:
                    break  # Last page
                    
                offset += page_size
                
            except Exception as e:
                logger.error(f"Error fetching markets at offset {offset}: {e}")
                break
        
        logger.info(f"Total markets fetched: {len(all_markets)}")
        return all_markets[:max_markets]
    
    def get_current_events(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get active, non-closed, non-archived events"""
        return self.get_events(
            querystring_params={
                "active": True,
                "closed": False,
                "archived": False,
                "limit": limit,
            }
        )
    
    def get_tradeable_markets(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get markets with order book enabled"""
        return self.get_markets(
            querystring_params={
                "active": True,
                "closed": False,
                "archived": False,
                "enableOrderBook": True,
                "limit": limit,
            }
        )
    
    def get_market(self, market_id: int) -> Optional[Dict[str, Any]]:
        """
        Get specific market by ID
        
        Args:
            market_id: Market ID
            
        Returns:
            Market data dictionary or None
        """
        try:
            url = f"{self.gamma_markets_endpoint}/{market_id}"
            response = httpx.get(url, timeout=30)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            logger.error(f"Error fetching market {market_id}: {e}")
            return None
    
    def get_event(self, event_id: int) -> Optional[Dict[str, Any]]:
        """
        Get specific event by ID
        
        Args:
            event_id: Event ID
            
        Returns:
            Event data dictionary or None
        """
        try:
            url = f"{self.gamma_events_endpoint}/{event_id}"
            response = httpx.get(url, timeout=30)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            logger.error(f"Error fetching event {event_id}: {e}")
            return None
    
    def search_markets(
        self,
        query: str,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Search markets by text query
        
        Args:
            query: Search query
            limit: Maximum results
            
        Returns:
            List of matching markets
        """
        markets = self.get_current_markets(limit=500)
        
        # Filter by query in question or description
        query_lower = query.lower()
        matching = []
        
        for market in markets:
            question = market.get("question", "").lower()
            description = market.get("description", "").lower()
            
            if query_lower in question or query_lower in description:
                matching.append(market)
                
            if len(matching) >= limit:
                break
                
        return matching
    
    def get_high_volume_markets(
        self,
        min_volume: float = 10000,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get markets with high trading volume
        
        Args:
            min_volume: Minimum volume threshold
            limit: Maximum number of markets
            
        Returns:
            List of high volume markets sorted by volume
        """
        markets = self.get_current_markets(limit=500)
        
        # Filter and sort by volume
        high_volume = [
            m for m in markets
            if float(m.get("volume", 0) or 0) >= min_volume
        ]
        
        high_volume.sort(key=lambda x: float(x.get("volume", 0) or 0), reverse=True)
        
        return high_volume[:limit]
    
    def get_high_liquidity_markets(
        self,
        min_liquidity: float = 5000,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get markets with high liquidity
        
        Args:
            min_liquidity: Minimum liquidity threshold
            limit: Maximum number of markets
            
        Returns:
            List of high liquidity markets
        """
        markets = self.get_current_markets(limit=500)
        
        # Filter and sort by liquidity
        high_liq = [
            m for m in markets
            if float(m.get("liquidity", 0) or 0) >= min_liquidity
        ]
        
        high_liq.sort(key=lambda x: float(x.get("liquidity", 0) or 0), reverse=True)
        
        return high_liq[:limit]
