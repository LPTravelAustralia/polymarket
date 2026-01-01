"""
Superforecaster AI Agent
Based on Tetlock's superforecasting methodology
Implements structured prediction framework for Polymarket
"""
import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from src.core.config import Config

logger = logging.getLogger(__name__)


class SuperforecasterPrompts:
    """Prompt templates based on official Polymarket agents framework"""
    
    @staticmethod
    def superforecaster_analysis(
        question: str,
        description: str,
        outcomes: List[str]
    ) -> str:
        """
        Generate superforecaster analysis prompt
        Uses Tetlock's 5-step methodology
        """
        return f"""
You are a Superforecaster tasked with correctly predicting the likelihood of events.
Use the following systematic process to develop an accurate prediction:

**QUESTION:** {question}
**DESCRIPTION:** {description}
**POSSIBLE OUTCOMES:** {', '.join(outcomes)}

Follow these key steps in your analysis:

1. **Breaking Down the Question:**
   - Decompose the question into smaller, more manageable parts
   - Identify the key components that need to be addressed
   - What are the critical factors that will determine the outcome?

2. **Gathering Information:**
   - Consider diverse sources of information
   - Look for both quantitative data and qualitative insights
   - What recent news or expert analyses are relevant?

3. **Consider Base Rates:**
   - Use statistical baselines or historical averages as a starting point
   - Compare the current situation to similar past events
   - What is the benchmark probability based on history?

4. **Identify and Evaluate Factors:**
   - List factors that could influence the outcome
   - Assess the impact of each factor (positive and negative)
   - Weigh these factors using evidence, avoiding over-reliance on any single piece

5. **Think Probabilistically:**
   - Express predictions in terms of probabilities, not certainties
   - Assign likelihoods to different outcomes
   - Embrace uncertainty - all forecasts are probabilistic

**OUTPUT FORMAT:**
Provide your analysis, then conclude with:
"PREDICTION: [OUTCOME] with probability [0.XX]"
"""
    
    @staticmethod
    def trade_decision(
        prediction: str,
        outcomes: List[str],
        outcome_prices: List[str]
    ) -> str:
        """Generate trade decision prompt based on prediction"""
        return f"""
You are an expert trader on Polymarket prediction markets.

**YOUR PREDICTION:** {prediction}
**AVAILABLE OUTCOMES:** {outcomes}
**CURRENT MARKET PRICES:** {outcome_prices}

Based on your prediction, determine if there's a profitable trading opportunity:

1. Compare your predicted probability to the current market price
2. If your prediction differs significantly from market price (edge > 5%), there may be an opportunity
3. Consider position sizing based on confidence level

**TRADING RULES:**
- Only trade if you have at least 5% edge (your probability vs market price)
- Size positions based on confidence: low (5%), medium (10%), high (20%) of available funds
- BUY if market underprices the outcome, SELL if market overprices

**OUTPUT FORMAT:**
```
action: BUY or SELL or HOLD
outcome: [which outcome]
price: [target price 0.00-1.00]
size: [percentage of funds 0.00-0.20]
confidence: [low/medium/high]
edge: [your edge percentage]
reasoning: [brief explanation]
```
"""
    
    @staticmethod
    def market_filter() -> str:
        """Prompt for filtering markets to trade"""
        return """
You are an AI assistant for analyzing prediction markets.
You will be provided with market data from Polymarket.

Polymarket is an online prediction market where users bet on outcomes of future events
in topics like politics, sports, entertainment, and economics.

Analyze the markets and filter for ones that:
1. Have clear, verifiable resolution criteria
2. Have sufficient liquidity for trading
3. Have topics you can form educated opinions on
4. Have reasonable time horizons (not too far in future)
5. Show potential for mispricing (edge opportunities)

For each recommended market, explain why it's a good trading candidate.
"""

    @staticmethod
    def sentiment_analysis(text: str, question: str) -> str:
        """Prompt for sentiment analysis of relevant text"""
        return f"""
You are a political scientist trained in media analysis.

**QUESTION:** {question}

**TEXT TO ANALYZE:**
{text}

Analyze this text and provide:
1. Overall sentiment toward the event occurring (positive/negative/neutral)
2. Key insights that affect probability
3. Confidence in the analysis (low/medium/high)

Output a sentiment score between 0 and 1, where:
- 0 = strongly suggests event will NOT occur
- 0.5 = neutral/uncertain
- 1 = strongly suggests event WILL occur

**FORMAT:**
SENTIMENT_SCORE: [0.00-1.00]
CONFIDENCE: [low/medium/high]
KEY_INSIGHTS: [bullet points]
"""


class SuperforecasterAgent:
    """
    AI agent implementing Superforecaster methodology
    for prediction market analysis and trading
    """
    
    def __init__(self, config: Config, model: str = "gpt-4"):
        """
        Initialize Superforecaster agent
        
        Args:
            config: Configuration object
            model: OpenAI model to use
        """
        self.config = config
        self.prompts = SuperforecasterPrompts()
        
        # Initialize LLM
        if config.openai_api_key:
            self.llm = ChatOpenAI(
                model=model,
                temperature=0.1,  # Low temperature for consistent predictions
                api_key=config.openai_api_key
            )
        else:
            self.llm = None
            logger.warning("No OpenAI API key - AI predictions disabled")
    
    def analyze_market(
        self,
        question: str,
        description: str,
        outcomes: List[str],
        current_prices: Optional[List[float]] = None
    ) -> Dict[str, Any]:
        """
        Perform superforecaster analysis on a market
        
        Args:
            question: Market question
            description: Market description
            outcomes: List of possible outcomes
            current_prices: Current market prices for outcomes
            
        Returns:
            Analysis result with prediction and confidence
        """
        if not self.llm:
            return {
                "error": "AI not available",
                "prediction": None,
                "confidence": None
            }
        
        try:
            # Step 1: Superforecaster analysis
            analysis_prompt = self.prompts.superforecaster_analysis(
                question, description, outcomes
            )
            
            messages = [
                SystemMessage(content="You are an expert Superforecaster."),
                HumanMessage(content=analysis_prompt)
            ]
            
            response = self.llm.invoke(messages)
            analysis = response.content
            
            # Parse prediction from analysis
            prediction = self._parse_prediction(analysis, outcomes)
            
            return {
                "question": question,
                "outcomes": outcomes,
                "current_prices": current_prices,
                "analysis": analysis,
                "prediction": prediction,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Analysis error: {e}")
            return {
                "error": str(e),
                "prediction": None
            }
    
    def get_trade_recommendation(
        self,
        analysis: Dict[str, Any],
        outcome_prices: List[str]
    ) -> Dict[str, Any]:
        """
        Get trade recommendation based on analysis
        
        Args:
            analysis: Market analysis from analyze_market
            outcome_prices: Current market prices
            
        Returns:
            Trade recommendation
        """
        if not self.llm or "error" in analysis:
            return {"action": "HOLD", "reason": "Analysis not available"}
        
        try:
            trade_prompt = self.prompts.trade_decision(
                prediction=analysis.get("analysis", ""),
                outcomes=analysis.get("outcomes", []),
                outcome_prices=outcome_prices
            )
            
            messages = [
                SystemMessage(content="You are an expert prediction market trader."),
                HumanMessage(content=trade_prompt)
            ]
            
            response = self.llm.invoke(messages)
            recommendation = self._parse_trade_recommendation(response.content)
            
            return recommendation
            
        except Exception as e:
            logger.error(f"Trade recommendation error: {e}")
            return {"action": "HOLD", "reason": str(e)}
    
    def filter_markets(
        self,
        markets: List[Dict[str, Any]],
        max_markets: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Filter markets for best trading opportunities
        
        Args:
            markets: List of market data
            max_markets: Maximum number to return
            
        Returns:
            Filtered list of markets
        """
        if not self.llm:
            # Simple filter without AI
            return self._simple_filter(markets, max_markets)
        
        try:
            # Use AI to filter markets
            market_summaries = self._summarize_markets(markets[:20])
            
            filter_prompt = self.prompts.market_filter()
            
            messages = [
                SystemMessage(content=filter_prompt),
                HumanMessage(content=f"Markets to analyze:\n{market_summaries}")
            ]
            
            response = self.llm.invoke(messages)
            
            # Parse recommended market IDs from response
            recommended_ids = self._parse_market_ids(response.content, markets)
            
            return [m for m in markets if m.get("id") in recommended_ids][:max_markets]
            
        except Exception as e:
            logger.error(f"Filter error: {e}")
            return self._simple_filter(markets, max_markets)
    
    def _parse_prediction(
        self,
        analysis: str,
        outcomes: List[str]
    ) -> Optional[Dict[str, Any]]:
        """Parse prediction from analysis text"""
        try:
            # Look for PREDICTION: pattern
            import re
            
            pattern = r"PREDICTION:\s*(.+?)\s+with\s+probability\s+(\d*\.?\d+)"
            match = re.search(pattern, analysis, re.IGNORECASE)
            
            if match:
                outcome = match.group(1).strip()
                probability = float(match.group(2))
                
                return {
                    "outcome": outcome,
                    "probability": probability
                }
            
            return None
            
        except Exception:
            return None
    
    def _parse_trade_recommendation(self, text: str) -> Dict[str, Any]:
        """Parse trade recommendation from response"""
        try:
            import re
            
            result = {
                "action": "HOLD",
                "outcome": None,
                "price": None,
                "size": None,
                "confidence": None,
                "edge": None,
                "reasoning": None,
                "raw_response": text
            }
            
            # Parse each field
            action_match = re.search(r"action:\s*(BUY|SELL|HOLD)", text, re.IGNORECASE)
            if action_match:
                result["action"] = action_match.group(1).upper()
            
            outcome_match = re.search(r"outcome:\s*(.+?)(?:\n|$)", text, re.IGNORECASE)
            if outcome_match:
                result["outcome"] = outcome_match.group(1).strip()
            
            price_match = re.search(r"price:\s*(\d*\.?\d+)", text, re.IGNORECASE)
            if price_match:
                result["price"] = float(price_match.group(1))
            
            size_match = re.search(r"size:\s*(\d*\.?\d+)", text, re.IGNORECASE)
            if size_match:
                result["size"] = float(size_match.group(1))
            
            conf_match = re.search(r"confidence:\s*(low|medium|high)", text, re.IGNORECASE)
            if conf_match:
                result["confidence"] = conf_match.group(1).lower()
            
            edge_match = re.search(r"edge:\s*(\d*\.?\d+)%?", text, re.IGNORECASE)
            if edge_match:
                result["edge"] = float(edge_match.group(1))
            
            reason_match = re.search(r"reasoning:\s*(.+?)(?:\n|$)", text, re.IGNORECASE | re.DOTALL)
            if reason_match:
                result["reasoning"] = reason_match.group(1).strip()
            
            return result
            
        except Exception as e:
            return {"action": "HOLD", "reason": str(e)}
    
    def _simple_filter(
        self,
        markets: List[Dict[str, Any]],
        max_markets: int
    ) -> List[Dict[str, Any]]:
        """Simple market filter based on liquidity and volume"""
        # Sort by liquidity * volume
        scored = []
        for m in markets:
            liq = float(m.get("liquidity", 0) or 0)
            vol = float(m.get("volume", 0) or 0)
            score = liq * vol
            scored.append((score, m))
        
        scored.sort(reverse=True)
        return [m for _, m in scored[:max_markets]]
    
    def _summarize_markets(self, markets: List[Dict[str, Any]]) -> str:
        """Create text summary of markets for AI analysis"""
        summaries = []
        for m in markets:
            summary = (
                f"ID: {m.get('id')}\n"
                f"Question: {m.get('question', 'N/A')}\n"
                f"Outcomes: {m.get('outcomes', [])}\n"
                f"Prices: {m.get('outcomePrices', [])}\n"
                f"Liquidity: ${m.get('liquidity', 0):,.0f}\n"
                f"Volume: ${m.get('volume', 0):,.0f}\n"
                f"End Date: {m.get('endDate', 'N/A')}\n"
                "---"
            )
            summaries.append(summary)
        
        return "\n".join(summaries)
    
    def _parse_market_ids(
        self,
        response: str,
        markets: List[Dict[str, Any]]
    ) -> List[int]:
        """Parse market IDs from AI response"""
        import re
        
        # Find all numbers that could be IDs
        potential_ids = re.findall(r'\b(\d+)\b', response)
        
        # Filter to valid market IDs
        valid_ids = {m.get("id") for m in markets}
        
        return [int(pid) for pid in potential_ids if int(pid) in valid_ids]
