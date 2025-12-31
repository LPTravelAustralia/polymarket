"""
Base agent class for Polymarket trading bots
"""
import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any

from src.core.client import PolymarketClient
from src.core.config import Config
from src.core.market_monitor import MarketMonitor
from src.core.fee_collector import FeeCollector

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """
    Base class for all trading agents
    """
    
    def __init__(self, config: Config):
        """
        Initialize base agent
        
        Args:
            config: Configuration object
        """
        self.config = config
        self.client = PolymarketClient(config)
        self.monitor = MarketMonitor(self.client, config)
        self.fee_collector = FeeCollector(config)
        
        self.positions: Dict[str, Any] = {}
        self.trade_history: List[Dict[str, Any]] = []
        self.total_profit_loss = 0.0
    
    @abstractmethod
    def analyze_market(self, market: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze a market and return trading signal
        
        Args:
            market: Market data
            
        Returns:
            Analysis result with trading signal
        """
        pass
    
    @abstractmethod
    def generate_trading_signal(self, analysis: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Generate trading signal from analysis
        
        Args:
            analysis: Market analysis
            
        Returns:
            Trading signal or None
        """
        pass
    
    def execute_trade(
        self,
        token_id: str,
        side: str,
        size: float,
        price: float
    ) -> Optional[Dict[str, Any]]:
        """
        Execute a trade
        
        Args:
            token_id: Token to trade
            side: "BUY" or "SELL"
            size: Trade size
            price: Trade price
            
        Returns:
            Trade execution result
        """
        # Check risk limits
        if not self._check_risk_limits(size, price):
            logger.warning("Trade rejected: exceeds risk limits")
            return None
        
        # Place order
        result = self.client.place_order(
            token_id=token_id,
            side=side,
            price=price,
            size=size
        )
        
        if result:
            # Record trade
            trade_record = {
                "token_id": token_id,
                "side": side,
                "size": size,
                "price": price,
                "result": result
            }
            self.trade_history.append(trade_record)
            
            # Calculate and collect fees if profitable
            if side == "SELL":
                profit = self._calculate_trade_profit(token_id, size, price)
                if profit > 0:
                    fee = self.fee_collector.calculate_fee(profit)
                    self.fee_collector.collect_fee(
                        from_address=self.config.wallet_address,
                        amount=fee,
                        transaction_hash=result.get("transaction_hash")
                    )
        
        return result
    
    def _check_risk_limits(self, size: float, price: float) -> bool:
        """
        Check if trade is within risk limits
        
        Args:
            size: Trade size
            price: Trade price
            
        Returns:
            True if within limits, False otherwise
        """
        trade_value = size * price
        
        # Check max position size
        if trade_value > self.config.max_position_size:
            return False
        
        # Check percentage of portfolio
        balance = self.client.get_balance()
        total_balance = sum(balance.values())
        
        if total_balance > 0:
            risk_ratio = trade_value / total_balance
            if risk_ratio > self.config.risk_percentage:
                return False
        
        return True
    
    def _calculate_trade_profit(self, token_id: str, size: float, sell_price: float) -> float:
        """
        Calculate profit from a trade
        
        Args:
            token_id: Token ID
            size: Trade size
            sell_price: Sell price
            
        Returns:
            Profit amount
        """
        # Find matching buy position
        position = self.positions.get(token_id)
        if not position:
            return 0.0
        
        buy_price = position.get("avg_price", 0)
        profit = (sell_price - buy_price) * size
        
        return profit
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """
        Get performance statistics
        
        Returns:
            Performance metrics
        """
        total_trades = len(self.trade_history)
        winning_trades = sum(1 for trade in self.trade_history if trade.get("profit", 0) > 0)
        win_rate = winning_trades / total_trades if total_trades > 0 else 0
        
        return {
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "win_rate": win_rate,
            "total_profit_loss": self.total_profit_loss,
            "total_fees_collected": self.fee_collector.get_total_fees()
        }
    
    def run(self):
        """
        Main agent loop
        """
        logger.info(f"Starting {self.__class__.__name__}")
        
        try:
            # Discover markets
            markets = self.monitor.discover_markets()
            
            for market in markets:
                # Analyze market
                analysis = self.analyze_market(market)
                
                # Generate trading signal
                signal = self.generate_trading_signal(analysis)
                
                # Execute trade if signal is generated
                if signal and self.config.auto_trade:
                    self.execute_trade(
                        token_id=signal["token_id"],
                        side=signal["side"],
                        size=signal["size"],
                        price=signal["price"]
                    )
        
        except Exception as e:
            logger.error(f"Error in agent run: {e}")
            raise
