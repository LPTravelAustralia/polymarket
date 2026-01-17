"""
Enhanced Trading Agent
Combines all components for autonomous trading
Based on official Polymarket agents framework patterns
"""
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from decimal import Decimal

from src.core.config import Config
from src.core.client import PolymarketClient
from src.core.gamma_client import GammaMarketClient
from src.core.fee_collector import FeeCollector
from src.agents.superforecaster import SuperforecasterAgent

logger = logging.getLogger(__name__)


class EnhancedTradingAgent:
    """
    Comprehensive trading agent that:
    1. Discovers markets via Gamma API
    2. Analyzes using Superforecaster methodology
    3. Executes trades via CLOB API
    4. Collects fees on profitable trades
    """
    
    def __init__(self, config: Config):
        """
        Initialize enhanced trading agent
        
        Args:
            config: Configuration object
        """
        self.config = config
        
        # Initialize clients
        self.clob_client = PolymarketClient(config)
        self.gamma_client = GammaMarketClient(config)
        self.fee_collector = FeeCollector(config)
        self.ai_agent = SuperforecasterAgent(config)
        
        # Trading state
        self.positions: Dict[str, Dict] = {}
        self.trade_history: List[Dict] = []
        self.total_pnl = Decimal("0")
        
        logger.info("Enhanced Trading Agent initialized")
    
    def discover_opportunities(
        self,
        min_liquidity: float = 5000,
        min_volume: float = 1000,
        max_markets: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Discover trading opportunities from Gamma API
        
        Args:
            min_liquidity: Minimum market liquidity
            min_volume: Minimum market volume
            max_markets: Maximum markets to return
            
        Returns:
            List of market opportunities
        """
        logger.info("Discovering trading opportunities...")
        
        # Get current tradeable markets
        markets = self.gamma_client.get_tradeable_markets(limit=100)
        
        # Filter by liquidity and volume
        filtered = []
        for market in markets:
            liquidity = float(market.get("liquidity", 0) or 0)
            volume = float(market.get("volume", 0) or 0)
            
            if liquidity >= min_liquidity and volume >= min_volume:
                # Add opportunity score
                market["opportunity_score"] = self._calculate_opportunity_score(market)
                filtered.append(market)
        
        # Sort by opportunity score
        filtered.sort(key=lambda x: x.get("opportunity_score", 0), reverse=True)
        
        logger.info(f"Found {len(filtered)} opportunities matching criteria")
        return filtered[:max_markets]
    
    def analyze_opportunities(
        self,
        markets: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Analyze markets using Superforecaster AI
        
        Args:
            markets: List of markets to analyze
            
        Returns:
            Markets with AI analysis attached
        """
        logger.info(f"Analyzing {len(markets)} markets with AI...")
        
        analyzed = []
        for market in markets:
            try:
                analysis = self.ai_agent.analyze_market(
                    question=market.get("question", ""),
                    description=market.get("description", ""),
                    outcomes=market.get("outcomes", ["Yes", "No"]),
                    current_prices=[
                        float(p) for p in market.get("outcomePrices", [0.5, 0.5])
                    ]
                )
                
                market["ai_analysis"] = analysis
                
                # Get trade recommendation
                if analysis.get("prediction"):
                    recommendation = self.ai_agent.get_trade_recommendation(
                        analysis=analysis,
                        outcome_prices=market.get("outcomePrices", [])
                    )
                    market["trade_recommendation"] = recommendation
                
                analyzed.append(market)
                
            except Exception as e:
                logger.error(f"Error analyzing market {market.get('id')}: {e}")
                market["ai_analysis"] = {"error": str(e)}
                analyzed.append(market)
        
        return analyzed
    
    def execute_strategy(
        self,
        strategy: str = "one_best_trade"
    ) -> Optional[Dict[str, Any]]:
        """
        Execute a trading strategy
        
        Args:
            strategy: Strategy name ("one_best_trade", "diversified", etc.)
            
        Returns:
            Trade result or None
        """
        if self.config.dry_run:
            logger.info("DRY RUN mode - no real trades will be executed")
        
        if strategy == "one_best_trade":
            return self._execute_one_best_trade()
        elif strategy == "diversified":
            return self._execute_diversified_strategy()
        else:
            logger.error(f"Unknown strategy: {strategy}")
            return None
    
    def _execute_one_best_trade(self) -> Optional[Dict[str, Any]]:
        """
        Execute the One Best Trade strategy
        
        Flow:
        1. Discover opportunities
        2. Analyze with AI
        3. Select best trade
        4. Execute
        """
        logger.info("Executing One Best Trade strategy...")
        
        # Step 1: Discover
        opportunities = self.discover_opportunities(
            min_liquidity=self.config.min_liquidity,
            max_markets=20
        )
        
        if not opportunities:
            logger.warning("No opportunities found")
            return None
        
        # Step 2: Analyze
        analyzed = self.analyze_opportunities(opportunities[:5])
        
        # Step 3: Find best trade
        best_trade = None
        best_edge = 0
        
        for market in analyzed:
            rec = market.get("trade_recommendation", {})
            if rec.get("action") in ["BUY", "SELL"]:
                edge = rec.get("edge", 0) or 0
                if edge > best_edge:
                    best_edge = edge
                    best_trade = {
                        "market": market,
                        "recommendation": rec
                    }
        
        if not best_trade:
            logger.info("No actionable trades found")
            return {"status": "no_trade", "reason": "No sufficient edge found"}
        
        # Step 4: Execute
        return self._execute_trade(
            market=best_trade["market"],
            recommendation=best_trade["recommendation"]
        )
    
    def _execute_diversified_strategy(self) -> Dict[str, Any]:
        """Execute diversified strategy across multiple markets"""
        logger.info("Executing Diversified strategy...")
        
        # Get and analyze opportunities
        opportunities = self.discover_opportunities(max_markets=10)
        analyzed = self.analyze_opportunities(opportunities)
        
        trades = []
        for market in analyzed:
            rec = market.get("trade_recommendation", {})
            if rec.get("action") in ["BUY", "SELL"] and (rec.get("edge", 0) or 0) >= 5:
                # Reduce size for diversification
                rec["size"] = min(rec.get("size", 0.1) or 0.1, 0.05)
                result = self._execute_trade(market, rec)
                trades.append(result)
        
        return {
            "strategy": "diversified",
            "trades_attempted": len(analyzed),
            "trades_executed": len([t for t in trades if t.get("status") == "executed"]),
            "trades": trades
        }
    
    def _execute_trade(
        self,
        market: Dict[str, Any],
        recommendation: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute a single trade
        
        Args:
            market: Market data
            recommendation: Trade recommendation
            
        Returns:
            Trade result
        """
        action = recommendation.get("action", "HOLD")
        outcome = recommendation.get("outcome", "Yes")
        price = recommendation.get("price", 0.5)
        size_pct = recommendation.get("size", 0.1)
        
        if action == "HOLD":
            return {"status": "skipped", "reason": "HOLD recommendation"}
        
        # Calculate trade size
        trade_size = self.config.default_trade_size * size_pct * 10  # Scale up
        
        # Get token ID for the outcome
        clob_token_ids = market.get("clobTokenIds", [])
        outcomes = market.get("outcomes", ["Yes", "No"])
        
        try:
            outcome_index = outcomes.index(outcome) if outcome in outcomes else 0
            token_id = clob_token_ids[outcome_index] if outcome_index < len(clob_token_ids) else None
        except (ValueError, IndexError):
            token_id = clob_token_ids[0] if clob_token_ids else None
        
        if not token_id:
            return {"status": "error", "reason": "Could not determine token ID"}
        
        # Execute trade
        trade_result = {
            "market_id": market.get("id"),
            "question": market.get("question"),
            "action": action,
            "outcome": outcome,
            "price": price,
            "size": trade_size,
            "token_id": token_id,
            "timestamp": datetime.now().isoformat(),
            "edge": recommendation.get("edge"),
            "confidence": recommendation.get("confidence")
        }
        
        if self.config.dry_run:
            trade_result["status"] = "dry_run"
            logger.info(f"DRY RUN: Would {action} {trade_size} of {outcome} at {price}")
        else:
            try:
                order_result = self.clob_client.place_order(
                    token_id=token_id,
                    side=action,
                    price=price,
                    size=trade_size
                )
                trade_result["status"] = "executed"
                trade_result["order_result"] = order_result
                
                # Track position
                self._update_position(market, trade_result)
                
            except Exception as e:
                trade_result["status"] = "error"
                trade_result["error"] = str(e)
                logger.error(f"Trade execution error: {e}")
        
        self.trade_history.append(trade_result)
        return trade_result
    
    def _calculate_opportunity_score(self, market: Dict[str, Any]) -> float:
        """Calculate opportunity score for a market"""
        liquidity = float(market.get("liquidity", 0) or 0)
        volume = float(market.get("volume", 0) or 0)
        spread = float(market.get("spread", 1) or 1)
        
        # Score based on liquidity, volume, and tight spreads
        score = (liquidity * 0.4) + (volume * 0.4) + ((1 - spread) * 1000 * 0.2)
        
        return score
    
    def _update_position(self, market: Dict, trade: Dict):
        """Update position tracking after trade"""
        market_id = str(market.get("id"))
        
        if market_id not in self.positions:
            self.positions[market_id] = {
                "market": market,
                "entries": [],
                "total_size": 0,
                "avg_price": 0
            }
        
        pos = self.positions[market_id]
        pos["entries"].append(trade)
        
        # Update running position
        if trade["action"] == "BUY":
            pos["total_size"] += trade["size"]
        else:
            pos["total_size"] -= trade["size"]
    
    def get_portfolio_summary(self) -> Dict[str, Any]:
        """Get summary of current portfolio"""
        return {
            "positions": len(self.positions),
            "trade_count": len(self.trade_history),
            "total_pnl": float(self.total_pnl),
            "fee_collected": self.fee_collector.get_total_fees(),
            "active_positions": [
                {
                    "market_id": mid,
                    "question": pos["market"].get("question"),
                    "size": pos["total_size"]
                }
                for mid, pos in self.positions.items()
                if pos["total_size"] != 0
            ]
        }
    
    def close_position(self, market_id: str) -> Optional[Dict[str, Any]]:
        """Close a position and collect fees if profitable"""
        if market_id not in self.positions:
            return None
        
        pos = self.positions[market_id]
        
        # TODO: Implement position closing logic
        # This would involve:
        # 1. Getting current market price
        # 2. Placing opposite order to close
        # 3. Calculating P&L
        # 4. Collecting fee if profitable
        
        logger.info(f"Position closing for {market_id} - to be implemented")
        return {"status": "not_implemented"}
