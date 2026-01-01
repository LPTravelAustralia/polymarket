"""
Core Polymarket API client wrapper
"""
import logging
from typing import Dict, List, Optional, Any
from decimal import Decimal

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY, SELL

from src.core.config import Config

logger = logging.getLogger(__name__)


class PolymarketClient:
    """
    Wrapper around py-clob-client for Polymarket trading operations
    """
    
    def __init__(self, config: Config):
        """
        Initialize Polymarket client
        
        Args:
            config: Configuration object with API credentials
        """
        self.config = config
        self.client: Optional[ClobClient] = None
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize the CLOB client with credentials"""
        try:
            host = "https://clob.polymarket.com" if self.config.bot_mode == "mainnet" else "https://clob-dev.polymarket.com"
            
            self.client = ClobClient(
                host=host,
                key=self.config.polymarket_api_key,
                chain_id=self.config.chain_id,
                signature_type=0,  # EOA
                funder=self.config.wallet_address
            )
            logger.info("Polymarket client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Polymarket client: {e}")
            raise
    
    def get_markets(self, next_cursor: str = "MA==") -> List[Dict[str, Any]]:
        """
        Get list of active markets
        
        Args:
            next_cursor: Cursor for pagination (default starts from beginning)
            
        Returns:
            List of market data dictionaries
        """
        try:
            response = self.client.get_markets(next_cursor=next_cursor)
            # Response may be a dict with 'data' key or a list
            if isinstance(response, dict):
                return response.get('data', [])
            return response if response else []
        except Exception as e:
            logger.error(f"Error fetching markets: {e}")
            return []
    
    def get_market(self, condition_id: str) -> Optional[Dict[str, Any]]:
        """
        Get specific market by condition ID
        
        Args:
            condition_id: Market condition ID
            
        Returns:
            Market data dictionary or None
        """
        try:
            market = self.client.get_market(condition_id)
            return market
        except Exception as e:
            logger.error(f"Error fetching market {condition_id}: {e}")
            return None
    
    def get_orderbook(self, token_id: str) -> Dict[str, Any]:
        """
        Get orderbook for a specific token
        
        Args:
            token_id: Token ID
            
        Returns:
            Orderbook data with bids and asks
        """
        try:
            orderbook = self.client.get_order_book(token_id)
            return orderbook
        except Exception as e:
            logger.error(f"Error fetching orderbook for {token_id}: {e}")
            return {"bids": [], "asks": []}
    
    def place_order(
        self,
        token_id: str,
        side: str,
        price: float,
        size: float,
        order_type: str = "GTC"
    ) -> Optional[Dict[str, Any]]:
        """
        Place an order on Polymarket
        
        Args:
            token_id: Token ID to trade
            side: "BUY" or "SELL"
            price: Price per share (0-1)
            size: Number of shares
            order_type: Order type (GTC, FOK, etc.)
            
        Returns:
            Order response or None
        """
        if self.config.dry_run:
            logger.info(f"DRY RUN: Would place {side} order for {size} shares of {token_id} at {price}")
            return {
                "status": "dry_run",
                "side": side,
                "price": price,
                "size": size,
                "token_id": token_id
            }
        
        try:
            order_args = OrderArgs(
                token_id=token_id,
                price=price,
                size=size,
                side=BUY if side.upper() == "BUY" else SELL,
                order_type=OrderType.GTC if order_type == "GTC" else OrderType.FOK
            )
            
            response = self.client.create_order(order_args)
            logger.info(f"Order placed successfully: {response}")
            return response
        except Exception as e:
            logger.error(f"Error placing order: {e}")
            return None
    
    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an existing order
        
        Args:
            order_id: Order ID to cancel
            
        Returns:
            True if cancelled successfully, False otherwise
        """
        try:
            self.client.cancel_order(order_id)
            logger.info(f"Order {order_id} cancelled successfully")
            return True
        except Exception as e:
            logger.error(f"Error cancelling order {order_id}: {e}")
            return False
    
    def get_balance(self, asset_id: Optional[str] = None) -> Dict[str, float]:
        """
        Get account balance
        
        Args:
            asset_id: Specific asset ID (optional)
            
        Returns:
            Balance information
        """
        try:
            balances = self.client.get_balances()
            return balances
        except Exception as e:
            logger.error(f"Error fetching balance: {e}")
            return {}
    
    def get_open_orders(self) -> List[Dict[str, Any]]:
        """
        Get all open orders for the account
        
        Returns:
            List of open orders
        """
        try:
            orders = self.client.get_orders()
            return [order for order in orders if order.get("status") == "OPEN"]
        except Exception as e:
            logger.error(f"Error fetching open orders: {e}")
            return []
    
    def get_positions(self) -> List[Dict[str, Any]]:
        """
        Get all current positions
        
        Returns:
            List of positions
        """
        try:
            positions = self.client.get_positions()
            return positions
        except Exception as e:
            logger.error(f"Error fetching positions: {e}")
            return []
