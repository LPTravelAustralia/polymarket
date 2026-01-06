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
from langchain_anthropic import ChatAnthropic

from src.core.config import Config

logger = logging.getLogger(__name__)


# Try to import connectors (optional)
try:
    from src.connectors.news import NewsConnector
    from src.connectors.search import TavilySearchConnector, DuckDuckGoSearchConnector
    CONNECTORS_AVAILABLE = True
except ImportError:
    CONNECTORS_AVAILABLE = False
    logger.warning("Connectors not available")


class SuperforecasterPrompts:
    """Prompt templates based on official Polymarket agents framework"""
    
    @staticmethod
    def superforecaster_analysis(
        question: str,
        description: str,
        outcomes: List[str],
        news_context: Optional[str] = None,
        search_context: Optional[str] = None
    ) -> str:
        """
        Generate superforecaster analysis prompt
        Uses Tetlock's 5-step methodology with optional news/search context
        """
        context_section = ""
        if news_context:
            context_section += f"\n**RECENT NEWS:**\n{news_context}\n"
        if search_context:
            context_section += f"\n**WEB SEARCH RESULTS:**\n{search_context}\n"
        
        return f"""
You are a Superforecaster tasked with correctly predicting the likelihood of events.
Use the following systematic process to develop an accurate prediction:

**QUESTION:** {question}
**DESCRIPTION:** {description}
**POSSIBLE OUTCOMES:** {', '.join(outcomes)}
{context_section}
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
    def superforecaster_with_odds(
        question: str,
        description: str,
        outcomes: List[str],
        current_odds: List[float],
        news_context: Optional[str] = None
    ) -> str:
        """
        Enhanced prompt that includes current market odds for edge calculation
        """
        odds_str = ", ".join([f"{o}: {p:.0%}" for o, p in zip(outcomes, current_odds)])
        context = f"\n**RECENT NEWS:**\n{news_context}\n" if news_context else ""
        
        return f"""
You are a Superforecaster analyzing prediction markets to find mispricings.

**QUESTION:** {question}
**DESCRIPTION:** {description}
**OUTCOMES:** {', '.join(outcomes)}
**CURRENT MARKET ODDS:** {odds_str}
{context}
Your task is to:
1. Analyze the question using Tetlock's superforecasting methodology
2. Determine your own probability estimate for each outcome
3. Compare to market prices to identify edge

**ANALYSIS FRAMEWORK:**

1. **Outside View (Base Rates)**
   - What's the historical frequency of similar events?
   - What do prediction markets/polls typically say?
   
2. **Inside View (Specific Factors)**
   - What unique factors affect this specific situation?
   - What recent developments are relevant?
   
3. **Synthesis**
   - Weight outside and inside views appropriately
   - Adjust for known biases
   
4. **Calibration Check**
   - Are you overconfident? Underconfident?
   - Does your probability feel right given uncertainty?

**OUTPUT FORMAT:**
ANALYSIS: [Your detailed reasoning]
PREDICTED_PROBABILITY: [0.XX for first outcome]
MARKET_PRICE: [Current market price]
EDGE: [Your probability - Market price, as percentage]
CONFIDENCE: [LOW/MEDIUM/HIGH]
RECOMMENDATION: [BUY_YES/BUY_NO/HOLD]
"""
    
    @staticmethod
    def quick_probability_estimate(
        question: str,
        current_yes_price: float = 0.5
    ) -> str:
        """Quick probability estimate for fast scanning"""
        return f"""
You are a Superforecaster. Quickly estimate the probability for this prediction market:

QUESTION: {question}
CURRENT MARKET PRICE: {current_yes_price:.0%} YES

Consider:
1. Base rates for similar events
2. Recent relevant news
3. Key factors

Respond with ONLY:
PROBABILITY: [0.XX]
CONFIDENCE: [LOW/MEDIUM/HIGH]
BRIEF_REASON: [One sentence]
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
    
    def __init__(self, config: Config, model: str = "gpt-4", use_news: bool = True, use_search: bool = True):
        """
        Initialize Superforecaster agent
        
        Args:
            config: Configuration object
            model: OpenAI model to use
            use_news: Whether to fetch news context
            use_search: Whether to use web search
        """
        self.config = config
        self.prompts = SuperforecasterPrompts()
        self.use_news = use_news
        self.use_search = use_search
        
        # Initialize LLM: prefer Anthropic, fallback to OpenAI
        if config.anthropic_api_key:
            self.llm = ChatAnthropic(
                model=model,
                temperature=0.1,
                api_key=config.anthropic_api_key,
                max_tokens=256,
            )
            logger.info(f"Superforecaster using Anthropic model: {model}")
        elif config.openai_api_key:
            self.llm = ChatOpenAI(
                model=model,
                temperature=0.1,  # Low temperature for consistent predictions
                api_key=config.openai_api_key
            )
            logger.info(f"Superforecaster using OpenAI model: {model}")
        else:
            self.llm = None
            logger.warning("No AI API key - Superforecaster disabled")
        
        # Initialize connectors
        self.news_connector = None
        self.search_connector = None
        
        if CONNECTORS_AVAILABLE:
            if use_news:
                self.news_connector = NewsConnector()
            if use_search:
                self.search_connector = TavilySearchConnector()
    
    def _get_news_context(self, question: str) -> Optional[str]:
        """Get relevant news articles for market"""
        if not self.news_connector:
            return None
        
        try:
            return self.news_connector.get_market_context(question, limit=3)
        except Exception as e:
            logger.warning(f"Failed to get news context: {e}")
            return None
    
    def _get_search_context(self, question: str) -> Optional[str]:
        """Get web search context for market"""
        if not self.search_connector:
            return None
        
        try:
            return self.search_connector.get_market_context(question, max_results=3)
        except Exception as e:
            logger.warning(f"Failed to get search context: {e}")
            return None
    
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
            # Get external context
            news_context = self._get_news_context(question) if self.use_news else None
            search_context = self._get_search_context(question) if self.use_search else None
            
            # Step 1: Superforecaster analysis
            analysis_prompt = self.prompts.superforecaster_analysis(
                question, description, outcomes,
                news_context=news_context,
                search_context=search_context
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
                "news_context": news_context,
                "search_context": search_context,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Analysis error: {e}")
            return {
                "error": str(e),
                "prediction": None
            }
    
    def quick_analyze(
        self,
        question: str,
        current_yes_price: float = 0.5
    ) -> Dict[str, Any]:
        """
        Quick probability estimate for fast market scanning
        
        Args:
            question: Market question
            current_yes_price: Current YES price
            
        Returns:
            Quick analysis with probability and edge
        """
        if not self.llm:
            return {"error": "AI not available"}
        
        try:
            prompt = self.prompts.quick_probability_estimate(question, current_yes_price)
            
            messages = [
                SystemMessage(content="You are a Superforecaster. Be concise."),
                HumanMessage(content=prompt)
            ]
            
            response = self.llm.invoke(messages)
            result = self._parse_quick_estimate(response.content)
            
            # Calculate edge
            if result.get("probability"):
                result["edge"] = result["probability"] - current_yes_price
                result["recommendation"] = (
                    "BUY_YES" if result["edge"] > 0.05 else
                    "BUY_NO" if result["edge"] < -0.05 else
                    "HOLD"
                )
            
            return result
            
        except Exception as e:
            logger.error(f"Quick analysis error: {e}")
            return {"error": str(e)}
    
    def _parse_quick_estimate(self, text: str) -> Dict[str, Any]:
        """Parse quick estimate response"""
        import re
        
        result = {"raw_response": text}
        
        prob_match = re.search(r"PROBABILITY:\s*(\d*\.?\d+)", text, re.IGNORECASE)
        if prob_match:
            result["probability"] = float(prob_match.group(1))
        
        conf_match = re.search(r"CONFIDENCE:\s*(LOW|MEDIUM|HIGH)", text, re.IGNORECASE)
        if conf_match:
            result["confidence"] = conf_match.group(1).upper()
        
        reason_match = re.search(r"BRIEF_REASON:\s*(.+?)(?:\n|$)", text, re.IGNORECASE)
        if reason_match:
            result["reason"] = reason_match.group(1).strip()
        
        return result
    
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
