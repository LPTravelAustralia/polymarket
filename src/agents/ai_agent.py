"""
AI-powered prediction agent using LLMs
"""
import logging
import os
from datetime import datetime
from typing import Dict, Optional, Any
import json

from src.agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)


class AIAgent(BaseAgent):
    """
    Trading agent that uses AI/LLM for predictions
    """
    
    def __init__(self, config):
        super().__init__(config)
        self.llm_client = None
        self._initialize_llm()
    
    def _initialize_llm(self):
        """Initialize LLM client based on configuration"""
        if not self.config.use_ai_predictions:
            logger.info("AI predictions disabled")
            return
        
        try:
            if self.config.openai_api_key:
                from openai import OpenAI
                self.llm_client = OpenAI(api_key=self.config.openai_api_key)
                logger.info("OpenAI client initialized")
            elif self.config.anthropic_api_key:
                from anthropic import Anthropic
                self.llm_client = Anthropic(api_key=self.config.anthropic_api_key)
                logger.info("Anthropic client initialized")
            else:
                logger.warning("No AI API key configured")
        except Exception as e:
            logger.error(f"Failed to initialize LLM client: {e}")
    
    def analyze_market(self, market: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze market using AI predictions
        
        Args:
            market: Market data
            
        Returns:
            Analysis with AI predictions
        """
        condition_id = market.get("condition_id")
        question = market.get("question", "")
        description = market.get("description", "")
        tokens = market.get("tokens", [])
        
        analysis = {
            "condition_id": condition_id,
            "question": question,
            "tokens": []
        }
        
        # Get current market prices
        for token in tokens:
            token_id = token.get("token_id")
            depth = self.monitor.analyze_market_depth(token_id)
            spread_pct = depth.get("spread_percentage") or 0
            
            analysis["tokens"].append({
                "token_id": token_id,
                "outcome": token.get("outcome"),
                "market_price": depth.get("best_ask"),
                "best_bid": depth.get("best_bid"),
                "best_ask": depth.get("best_ask"),
                "spread_pct": spread_pct
            })
        
        # Get AI prediction if enabled
        if self.config.use_ai_predictions and self.llm_client:
            ai_prediction = self._get_ai_prediction(question, description, analysis["tokens"])
            analysis["ai_prediction"] = ai_prediction

            # Log calibration data even if we later skip trading
            self._log_calibration(
                condition_id=condition_id,
                tokens=analysis["tokens"],
                ai_prediction=ai_prediction
            )
        
        return analysis
    
    def _get_ai_prediction(
        self,
        question: str,
        description: str,
        tokens: list
    ) -> Dict[str, Any]:
        """
        Get AI prediction for market outcome
        
        Args:
            question: Market question
            description: Market description
            tokens: Token information
            
        Returns:
            AI prediction with confidence scores
        """
        try:
            # Create prompt for LLM
            prompt = self._create_prediction_prompt(question, description, tokens)
            
            if hasattr(self.llm_client, 'chat'):  # OpenAI
                response = self.llm_client.chat.completions.create(
                    model="gpt-4",
                    messages=[
                        {"role": "system", "content": "You are an expert prediction analyst for prediction markets. Analyze the question and provide probability estimates."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.7
                )
                prediction_text = response.choices[0].message.content
            else:  # Anthropic or other
                logger.warning("LLM prediction not fully implemented for this provider")
                return {"error": "Provider not supported"}
            
            # Parse prediction
            prediction = self._parse_prediction(prediction_text, tokens)
            return prediction
        
        except Exception as e:
            logger.error(f"Error getting AI prediction: {e}")
            return {"error": str(e)}
    
    def _create_prediction_prompt(
        self,
        question: str,
        description: str,
        tokens: list
    ) -> str:
        """Create prompt for LLM prediction"""
        outcomes = [token["outcome"] for token in tokens]
        market_prices = [token["market_price"] for token in tokens]
        
        prompt = f"""
Analyze this prediction market question and provide probability estimates:

Question: {question}
Description: {description}

Possible outcomes: {', '.join(outcomes)}
Current market prices: {', '.join(f"{o}: {p:.2f}" for o, p in zip(outcomes, market_prices))}

Please provide:
1. Your estimated probability for each outcome (must sum to 1.0)
2. Confidence level (0-1) in your prediction
3. Brief reasoning for your estimates
4. Whether you recommend buying any outcome (yes/no for each)

Format your response as JSON:
{{
    "predictions": [{{"outcome": "...", "probability": 0.X, "recommend_buy": true/false}}],
    "confidence": 0.X,
    "reasoning": "..."
}}
"""
        return prompt
    
    def _parse_prediction(self, prediction_text: str, tokens: list) -> Dict[str, Any]:
        """Parse LLM prediction response"""
        try:
            # Try to extract JSON from response
            start = prediction_text.find('{')
            end = prediction_text.rfind('}') + 1
            
            if start >= 0 and end > start:
                json_str = prediction_text[start:end]
                prediction = json.loads(json_str)
                return prediction
            else:
                return {"error": "Could not parse prediction"}
        
        except Exception as e:
            logger.error(f"Error parsing prediction: {e}")
            return {"error": str(e)}
    
    def generate_trading_signal(self, analysis: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Generate trading signal from AI analysis
        
        Args:
            analysis: Market analysis with AI predictions
            
        Returns:
            Trading signal or None
        """
        ai_prediction = analysis.get("ai_prediction")
        
        if not ai_prediction or "error" in ai_prediction:
            return None
        
        # Check confidence level
        confidence = ai_prediction.get("confidence", 0)
        if confidence < self.config.ai_min_confidence:
            return None
        
        # Find recommended outcome
        predictions = ai_prediction.get("predictions", [])
        tokens = analysis.get("tokens", [])
        
        for pred, token in zip(predictions, tokens):
            if pred.get("recommend_buy"):
                ai_prob = pred.get("probability", 0)
                market_price = token.get("market_price", 0)
                spread_pct = token.get("spread_pct", 0)
                edge = ai_prob - market_price

                # Require sufficient edge, tight spread, and valid prices
                if market_price is None or market_price <= 0:
                    continue
                if spread_pct is None:
                    spread_pct = 0
                if spread_pct > self.config.ai_max_spread_pct:
                    continue
                
                # Only buy if AI probability is significantly higher than market
                if edge >= self.config.ai_min_edge:
                    return {
                        "token_id": token["token_id"],
                        "side": "BUY",
                        "price": token["best_ask"],
                        "size": self.config.default_trade_size,
                        "reason": f"AI edge {edge:.2f} with confidence {confidence:.2f}; spread {spread_pct:.2f}%",
                        "ai_probability": ai_prob,
                        "edge": edge,
                        "confidence": confidence
                    }
        
        return None

    def _log_calibration(self, condition_id: str, tokens: list, ai_prediction: Dict[str, Any]) -> None:
        """Persist AI vs market comparison for later calibration."""
        if not ai_prediction or "predictions" not in ai_prediction:
            return

        try:
            dirpath = os.path.dirname(self.config.calibration_log_path) or "."
            os.makedirs(dirpath, exist_ok=True)
            rows = []
            predictions = ai_prediction.get("predictions", [])
            confidence = ai_prediction.get("confidence")

            for pred, token in zip(predictions, tokens):
                market_price = token.get("market_price")
                if market_price is None:
                    continue
                edge = pred.get("probability", 0) - market_price
                rows.append(
                    {
                        "timestamp": datetime.utcnow().isoformat(),
                        "condition_id": condition_id,
                        "token_id": token.get("token_id"),
                        "outcome": token.get("outcome"),
                        "market_price": market_price,
                        "ai_probability": pred.get("probability"),
                        "edge": edge,
                        "confidence": confidence,
                        "recommend_buy": pred.get("recommend_buy"),
                    }
                )

            if not rows:
                return

            header = [
                "timestamp",
                "condition_id",
                "token_id",
                "outcome",
                "market_price",
                "ai_probability",
                "edge",
                "confidence",
                "recommend_buy",
            ]

            file_exists = os.path.isfile(self.config.calibration_log_path)
            with open(self.config.calibration_log_path, "a", encoding="utf-8") as f:
                if not file_exists:
                    f.write(",".join(header) + "\n")
                for row in rows:
                    f.write(",".join(str(row[h]) if row[h] is not None else "" for h in header) + "\n")
        except Exception as e:
            logger.debug(f"Calibration log write failed: {e}")
