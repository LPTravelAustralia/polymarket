"""
Base agent class for Polymarket trading bots
"""
import logging
import time
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Tuple

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
        allowed, reason = self._check_risk_limits(size, price)
        if not allowed:
            logger.warning(
                "Trade rejected: risk limits",
                extra={
                    "token_id": token_id,
                    "side": side,
                    "size": size,
                    "price": price,
                    "reason": reason,
                },
            )
            return None
        
        # Place order
        logger.info(
            "Placing order",
            extra={"token_id": token_id, "side": side, "size": size, "price": price},
        )
        start_ts = time.time()
        result = self.client.place_order(
            token_id=token_id,
            side=side,
            price=price,
            size=size
        )
        end_ts = time.time()
        placement_ms = int((end_ts - start_ts) * 1000)
        
        if result:
            # Record trade
            trade_record = {
                "token_id": token_id,
                "side": side,
                "size": size,
                "price": price,
                "placement_ms": placement_ms,
                "result": result
            }
            self.trade_history.append(trade_record)

            logger.info(
                "Trade executed",
                extra={
                    "token_id": token_id,
                    "side": side,
                    "size": size,
                    "price": price,
                    "placement_ms": placement_ms,
                    "result": result,
                },
            )
            
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
                    logger.info(
                        "Collected performance fee",
                        extra={
                            "token_id": token_id,
                            "profit": profit,
                            "fee": fee,
                        },
                    )
        else:
            logger.error(
                "Order placement failed",
                extra={"token_id": token_id, "side": side, "size": size, "price": price},
            )
        
        return result
    
    def _check_risk_limits(self, size: float, price: float) -> Tuple[bool, str]:
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
            return False, "max_position_size"
        
        # Check percentage of portfolio
        balance = self.client.get_balance()
        total_balance = sum(balance.values())
        
        if total_balance > 0:
            risk_ratio = trade_value / total_balance
            if risk_ratio > self.config.risk_percentage:
                return False, "risk_percentage"
        
        return True, "ok"
    
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
            logger.info(
                "Discovered markets",
                extra={"count": len(markets), "min_liquidity": self.config.min_liquidity},
            )
            
            for market in markets:
                # Analyze market
                logger.debug(
                    "Analyzing market",
                    extra={
                        "condition_id": market.get("condition_id"),
                        "question": market.get("question"),
                    },
                )
                analysis = self.analyze_market(market)
                
                # Generate trading signal
                signal = self.generate_trading_signal(analysis)
                
                # Execute trade if signal is generated
                if signal and self.config.auto_trade:
                    logger.info(
                        "Generated trading signal",
                        extra={
                            "token_id": signal.get("token_id"),
                            "side": signal.get("side"),
                            "price": signal.get("price"),
                            "size": signal.get("size"),
                            "reason": signal.get("reason"),
                        },
                    )
                    self.execute_trade(
                        token_id=signal["token_id"],
                        side=signal["side"],
                        size=signal["size"],
                        price=signal["price"]
                    )
                else:
                    logger.debug(
                        "No actionable signal",
                        extra={
                            "condition_id": market.get("condition_id"),
                            "question": market.get("question"),
                        },
                    )
        
        except Exception as e:
            logger.error(f"Error in agent run: {e}")
            raise
