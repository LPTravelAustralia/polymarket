"""
Value Betting Agent
Finds markets where odds differ significantly from true probability
Uses multiple signals to estimate true probability
"""
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime

from src.core.config import Config
from src.agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)


@dataclass
class ValueOpportunity:
    """Represents a value betting opportunity"""
    market_id: str
    question: str
    current_price: float  # Market YES price
    estimated_prob: float  # Our estimated probability
    edge: float  # estimated_prob - current_price
    confidence: float
    side: str  # 'YES' or 'NO'
    signals: Dict[str, Any]


class ValueBettingAgent(BaseAgent):
    """
    Value Betting Strategy
    
    Core principle: Find markets where the current price differs
    significantly from the true probability. Uses multiple signals:
    
    1. Historical base rates
    2. Recent news sentiment
    3. Expert consensus
    4. Market inefficiencies (time of day, liquidity)
    
    Only trades when:
    - Edge > minimum threshold (e.g., 5%)
    - Confidence is high
    - Liquidity is sufficient
    """
    
    def __init__(self, config: Config):
        super().__init__(config)
        self.min_edge = config.min_edge if hasattr(config, 'min_edge') else 0.05
        self.min_confidence = 0.6
        self.min_liquidity = config.min_liquidity if hasattr(config, 'min_liquidity') else 1000
        
    async def analyze(self, market: Dict[str, Any]) -> Optional[ValueOpportunity]:
        """
        Analyze a market for value betting opportunities
        
        Args:
            market: Market data dictionary
            
        Returns:
            ValueOpportunity if found, None otherwise
        """
        try:
            question = market.get('question', '')
            current_yes_price = float(market.get('yes_price', 0.5))
            current_no_price = float(market.get('no_price', 0.5))
            liquidity = float(market.get('liquidity', 0))
            
            # Skip low liquidity markets
            if liquidity < self.min_liquidity:
                return None
            
            # Calculate signals
            signals = await self._calculate_signals(market)
            
            # Estimate true probability from signals
            estimated_prob = self._estimate_probability(signals)
            confidence = self._calculate_confidence(signals)
            
            # Calculate edge for both sides
            yes_edge = estimated_prob - current_yes_price
            no_edge = (1 - estimated_prob) - current_no_price
            
            # Choose best side
            if yes_edge > no_edge and yes_edge >= self.min_edge:
                edge = yes_edge
                side = 'YES'
            elif no_edge >= self.min_edge:
                edge = no_edge
                side = 'NO'
                estimated_prob = 1 - estimated_prob
            else:
                return None
            
            # Check confidence threshold
            if confidence < self.min_confidence:
                return None
            
            return ValueOpportunity(
                market_id=market.get('id', ''),
                question=question,
                current_price=current_yes_price if side == 'YES' else current_no_price,
                estimated_prob=estimated_prob,
                edge=edge,
                confidence=confidence,
                side=side,
                signals=signals
            )
            
        except Exception as e:
            logger.error(f"Error analyzing market: {e}")
            return None
    
    async def _calculate_signals(self, market: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate various signals for probability estimation"""
        signals = {
            'market_price': float(market.get('yes_price', 0.5)),
            'volume_ratio': 1.0,
            'time_factor': 1.0,
            'spread_signal': 0.0,
            'momentum': 0.0,
        }
        
        # Volume signal: High volume = more efficient pricing
        volume = float(market.get('volume', 0))
        volume_24h = float(market.get('volume_24h', 0))
        if volume > 0 and volume_24h > 0:
            signals['volume_ratio'] = min(volume_24h / volume, 1.0) if volume > volume_24h else 1.0
        
        # Time factor: Markets close to expiry are more accurate
        end_date_str = market.get('end_date')
        if end_date_str:
            try:
                end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
                hours_to_expiry = (end_date - datetime.now(end_date.tzinfo)).total_seconds() / 3600
                # More confidence as we approach expiry (but not too close)
                if hours_to_expiry > 24:
                    signals['time_factor'] = min(168 / hours_to_expiry, 2.0)
            except:
                pass
        
        # Spread signal: Wide spread = opportunity
        spread = float(market.get('spread', 0.02))
        signals['spread_signal'] = spread * 0.5  # Wide spread suggests mispricing
        
        return signals
    
    def _estimate_probability(self, signals: Dict[str, Any]) -> float:
        """
        Estimate true probability from signals
        
        In a full implementation, this would use:
        - AI model predictions
        - Historical base rates
        - News sentiment
        
        For now, we use the market price with adjustments
        """
        base_prob = signals.get('market_price', 0.5)
        
        # Adjust for spread (wide spread = uncertainty)
        spread_adj = signals.get('spread_signal', 0) * 0.5
        
        # Slight mean reversion for extreme prices
        if base_prob > 0.9:
            base_prob -= 0.02
        elif base_prob < 0.1:
            base_prob += 0.02
        
        return max(0.01, min(0.99, base_prob + spread_adj))
    
    def _calculate_confidence(self, signals: Dict[str, Any]) -> float:
        """Calculate confidence in our probability estimate"""
        confidence = 0.5  # Base confidence
        
        # Higher volume = higher confidence
        confidence += signals.get('volume_ratio', 0) * 0.2
        
        # Time factor
        confidence += min(signals.get('time_factor', 0) * 0.1, 0.2)
        
        return min(confidence, 0.95)
    
    def get_trade_recommendation(
        self,
        opportunity: ValueOpportunity,
        bankroll: float
    ) -> Dict[str, Any]:
        """
        Get trade recommendation with Kelly-optimal sizing
        """
        # Kelly criterion: f* = (bp - q) / b
        # where b = odds - 1, p = win prob, q = lose prob
        
        if opportunity.side == 'YES':
            price = opportunity.current_price
            win_prob = opportunity.estimated_prob
        else:
            price = 1 - opportunity.current_price
            win_prob = opportunity.estimated_prob
        
        lose_prob = 1 - win_prob
        odds = 1 / price if price > 0 else 0
        b = odds - 1
        
        if b > 0:
            kelly = (b * win_prob - lose_prob) / b
            # Use half-Kelly for safety
            kelly = max(0, kelly * 0.5)
            # Cap at 10% of bankroll
            kelly = min(kelly, 0.10)
        else:
            kelly = 0
        
        position_size = kelly * bankroll
        
        return {
            'action': 'BUY_' + opportunity.side,
            'market_id': opportunity.market_id,
            'size': round(position_size, 2),
            'price': opportunity.current_price,
            'edge': opportunity.edge,
            'confidence': opportunity.confidence,
            'kelly_fraction': kelly,
        }
