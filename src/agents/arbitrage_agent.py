"""
Arbitrage trading agent
"""
import logging
from typing import Dict, Optional, Any, List

from src.agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)


class ArbitrageAgent(BaseAgent):
    """
    Trading agent that exploits arbitrage opportunities
    """
    
    def analyze_market(self, market: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze market for arbitrage opportunities
        
        Args:
            market: Market data
            
        Returns:
            Analysis with arbitrage opportunities
        """
        condition_id = market.get("condition_id")
        tokens = market.get("tokens", [])
        
        analysis = {
            "condition_id": condition_id,
            "question": market.get("question"),
            "tokens": [],
            "total_probability": 0.0,
            "has_arbitrage": False
        }
        
        total_prob = 0.0
        
        for token in tokens:
            token_id = token.get("token_id")
            depth = self.monitor.analyze_market_depth(token_id)
            
            best_bid = depth.get("best_bid", 0)
            best_ask = depth.get("best_ask", 1)
            
            # Use best ask as implied probability
            implied_prob = best_ask
            total_prob += implied_prob
            
            analysis["tokens"].append({
                "token_id": token_id,
                "outcome": token.get("outcome"),
                "best_bid": best_bid,
                "best_ask": best_ask,
                "implied_probability": implied_prob
            })
        
        analysis["total_probability"] = total_prob
        
        # Arbitrage exists if total probability < 1 (underpriced market)
        # or if we can construct a guaranteed profit portfolio
        if total_prob < 0.98:
            analysis["has_arbitrage"] = True
            analysis["arbitrage_margin"] = 1.0 - total_prob
        
        return analysis
    
    def generate_trading_signal(self, analysis: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Generate arbitrage trading signal
        
        Args:
            analysis: Market analysis
            
        Returns:
            Trading signal or None
        """
        if not analysis.get("has_arbitrage"):
            return None
        
        arbitrage_margin = analysis.get("arbitrage_margin", 0)
        
        # Only trade if arbitrage margin is significant
        if arbitrage_margin < 0.02:  # Less than 2%
            return None
        
        # Buy all outcomes to create guaranteed profit
        tokens = analysis.get("tokens", [])
        
        # Return signal for the cheapest outcome
        cheapest = min(tokens, key=lambda x: x.get("best_ask", 1))
        
        return {
            "token_id": cheapest["token_id"],
            "side": "BUY",
            "price": cheapest["best_ask"],
            "size": self.config.default_trade_size,
            "reason": f"Arbitrage opportunity: {arbitrage_margin * 100:.2f}% margin",
            "arbitrage_margin": arbitrage_margin
        }
    
    def execute_arbitrage(self, analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Execute full arbitrage strategy (buy all outcomes)
        
        Args:
            analysis: Market analysis
            
        Returns:
            List of trade results
        """
        if not analysis.get("has_arbitrage"):
            return []
        
        tokens = analysis.get("tokens", [])
        results = []
        
        for token in tokens:
            result = self.execute_trade(
                token_id=token["token_id"],
                side="BUY",
                size=self.config.default_trade_size,
                price=token["best_ask"]
            )
            
            if result:
                results.append(result)
        
        return results
