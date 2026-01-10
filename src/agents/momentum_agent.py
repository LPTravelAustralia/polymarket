"""
Simple momentum-based trading agent
"""
import logging
from typing import Dict, Optional, Any

from src.agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)


class MomentumAgent(BaseAgent):
    """
    Trading agent based on price momentum
    """
    
    def analyze_market(self, market: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze market using momentum indicators
        
        Args:
            market: Market data
            
        Returns:
            Analysis with momentum indicators
        """
        condition_id = market.get("condition_id")
        tokens = market.get("tokens", [])
        
        analysis = {
            "condition_id": condition_id,
            "question": market.get("question"),
            "tokens": []
        }
        
        for token in tokens:
            token_id = token.get("token_id")
            
            # Get current market depth
            depth = self.monitor.analyze_market_depth(token_id)
            
            # Calculate momentum score (simplified)
            bid_ask_ratio = depth.get("bid_ask_ratio", 0)
            spread = depth.get("spread_percentage", 0)
            
            # Strong buying momentum if more bids than asks and tight spread
            momentum_score = bid_ask_ratio * (1 / (1 + spread)) if spread > 0 else 0
            
            analysis["tokens"].append({
                "token_id": token_id,
                "outcome": token.get("outcome"),
                "momentum_score": momentum_score,
                "best_bid": depth.get("best_bid"),
                "best_ask": depth.get("best_ask"),
                "spread": spread
            })
        
        return analysis
    
    def generate_trading_signal(self, analysis: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Generate trading signal from momentum analysis
        
        Args:
            analysis: Market analysis
            
        Returns:
            Trading signal or None
        """
        tokens = analysis.get("tokens", [])
        if not tokens:
            logger.debug(
                "No tokens available for signal",
                extra={
                    "condition_id": analysis.get("condition_id"),
                    "question": analysis.get("question"),
                },
            )
            return None
        
        # Find token with strongest momentum
        best_token = max(tokens, key=lambda x: x.get("momentum_score", 0))
        momentum_score = best_token.get("momentum_score", 0)
        
        # Only trade if momentum is strong enough
        if momentum_score < 1.5:
            logger.debug(
                "Momentum below threshold",
                extra={
                    "condition_id": analysis.get("condition_id"),
                    "token_id": best_token.get("token_id"),
                    "momentum_score": momentum_score,
                },
            )
            return None
        
        # Check spread is reasonable
        spread = best_token.get("spread", 0)
        if spread > 5.0:  # More than 5% spread
            logger.debug(
                "Spread too wide",
                extra={
                    "condition_id": analysis.get("condition_id"),
                    "token_id": best_token.get("token_id"),
                    "spread": spread,
                },
            )
            return None
        
        return {
            "token_id": best_token["token_id"],
            "side": "BUY",
            "price": best_token["best_ask"],
            "size": self.config.default_trade_size,
            "reason": f"Strong momentum (score: {momentum_score:.2f})"
        }
