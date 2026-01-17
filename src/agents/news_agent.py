"""
News Sentiment Trading Agent
Trades based on real-time news sentiment analysis
Uses multiple news sources and NLP for sentiment scoring
"""
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime, timedelta

from src.core.config import Config
from src.agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)

# Try to import connectors
try:
    from src.connectors.news import NewsConnector
    from src.connectors.search import TavilySearchConnector, DuckDuckGoSearchConnector
    CONNECTORS_AVAILABLE = True
except ImportError:
    CONNECTORS_AVAILABLE = False
    logger.warning("Connectors not available for news sentiment agent")


@dataclass
class SentimentSignal:
    """Represents a sentiment signal from news analysis"""
    market_id: str
    question: str
    sentiment_score: float  # -1 (very negative) to +1 (very positive)
    confidence: float
    article_count: int
    keywords: List[str]
    recent_headlines: List[str]
    signal: str  # 'BULLISH', 'BEARISH', 'NEUTRAL'


class NewsSentimentAgent(BaseAgent):
    """
    News Sentiment Trading Strategy
    
    Analyzes real-time news to identify sentiment shifts that
    may not yet be reflected in market prices.
    
    Key features:
    1. Multi-source news aggregation (NewsAPI, Tavily, DuckDuckGo)
    2. Keyword extraction from market questions
    3. Sentiment scoring using NLP
    4. Recency weighting (newer news = higher weight)
    5. Confidence based on article count and consistency
    """
    
    def __init__(self, config: Config):
        super().__init__(config)
        self.min_articles = 3
        self.min_confidence = 0.6
        self.sentiment_threshold = 0.3  # Min sentiment magnitude to trade
        
        # Initialize connectors if available
        self.news_connector = None
        self.search_connector = None
        
        if CONNECTORS_AVAILABLE:
            try:
                self.news_connector = NewsConnector()
                self.search_connector = TavilySearchConnector()
            except Exception as e:
                logger.warning(f"Failed to initialize connectors: {e}")
    
    def _extract_keywords(self, question: str) -> List[str]:
        """
        Extract search keywords from market question
        
        Example: "Will Trump win the 2024 election?" 
        -> ["Trump", "2024", "election", "win"]
        """
        # Remove common words
        stopwords = {
            'will', 'the', 'a', 'an', 'be', 'is', 'are', 'was', 'were',
            'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did',
            'shall', 'should', 'may', 'might', 'must', 'can', 'could',
            'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by', 'from',
            'or', 'and', 'not', 'this', 'that', 'these', 'those',
            'what', 'which', 'who', 'whom', 'whose', 'when', 'where',
            'why', 'how', 'before', 'after', 'during', 'above', 'below',
        }
        
        # Clean and tokenize
        words = question.replace('?', '').replace(',', '').split()
        
        # Filter and get unique keywords
        keywords = []
        for word in words:
            word_lower = word.lower()
            if word_lower not in stopwords and len(word) > 2:
                keywords.append(word)
        
        return keywords[:5]  # Limit to 5 keywords
    
    async def analyze(self, market: Dict[str, Any]) -> Optional[SentimentSignal]:
        """
        Analyze news sentiment for a market
        
        Args:
            market: Market data dictionary
            
        Returns:
            SentimentSignal if sufficient data, None otherwise
        """
        try:
            question = market.get('question', '')
            market_id = market.get('id', '')
            
            if not question:
                return None
            
            # Extract keywords
            keywords = self._extract_keywords(question)
            search_query = ' '.join(keywords)
            
            # Get news articles
            articles = await self._fetch_news(search_query)
            
            if len(articles) < self.min_articles:
                logger.debug(f"Not enough articles for {market_id}: {len(articles)}")
                return None
            
            # Analyze sentiment
            sentiment_score, confidence = self._analyze_sentiment(articles, keywords)
            
            # Determine signal
            if sentiment_score > self.sentiment_threshold:
                signal = 'BULLISH'
            elif sentiment_score < -self.sentiment_threshold:
                signal = 'BEARISH'
            else:
                signal = 'NEUTRAL'
            
            # Get headlines for display
            headlines = [a.get('title', '')[:100] for a in articles[:5]]
            
            return SentimentSignal(
                market_id=market_id,
                question=question,
                sentiment_score=sentiment_score,
                confidence=confidence,
                article_count=len(articles),
                keywords=keywords,
                recent_headlines=headlines,
                signal=signal
            )
            
        except Exception as e:
            logger.error(f"Error analyzing sentiment: {e}")
            return None
    
    async def _fetch_news(self, query: str) -> List[Dict[str, Any]]:
        """Fetch news from available sources"""
        articles = []
        
        # Try NewsAPI first
        if self.news_connector:
            try:
                news_articles = self.news_connector.search(query, days_back=7)
                articles.extend([
                    {
                        'title': a.title,
                        'content': a.description or a.content or '',
                        'source': a.source,
                        'published_at': a.published_at,
                    }
                    for a in news_articles
                ])
            except Exception as e:
                logger.debug(f"NewsAPI error: {e}")
        
        # Fallback to search if not enough articles
        if len(articles) < self.min_articles and self.search_connector:
            try:
                search_results = self.search_connector.search(query)
                articles.extend([
                    {
                        'title': r.title,
                        'content': r.content,
                        'source': r.url,
                        'published_at': None,
                    }
                    for r in search_results
                ])
            except Exception as e:
                logger.debug(f"Search error: {e}")
        
        return articles
    
    def _analyze_sentiment(
        self, 
        articles: List[Dict[str, Any]],
        keywords: List[str]
    ) -> tuple[float, float]:
        """
        Analyze sentiment from articles
        
        Returns:
            (sentiment_score, confidence) where:
            - sentiment_score: -1.0 to +1.0
            - confidence: 0.0 to 1.0
        """
        if not articles:
            return 0.0, 0.0
        
        # Simple keyword-based sentiment (would use NLP in production)
        positive_words = {
            'win', 'winning', 'success', 'successful', 'gain', 'gains',
            'rise', 'rising', 'up', 'higher', 'increase', 'increased',
            'positive', 'good', 'great', 'excellent', 'strong', 'surge',
            'breakthrough', 'approve', 'approved', 'pass', 'passed',
            'lead', 'leading', 'ahead', 'support', 'supports', 'backed',
            'confirmed', 'yes', 'likely', 'expected', 'favored',
        }
        
        negative_words = {
            'lose', 'losing', 'loss', 'fail', 'failed', 'failure',
            'fall', 'falling', 'down', 'lower', 'decrease', 'decreased',
            'negative', 'bad', 'poor', 'weak', 'collapse', 'crash',
            'reject', 'rejected', 'block', 'blocked', 'deny', 'denied',
            'behind', 'trailing', 'oppose', 'opposes', 'opposition',
            'unlikely', 'doubt', 'doubts', 'no', 'against',
        }
        
        total_positive = 0
        total_negative = 0
        total_relevance = 0
        
        for article in articles:
            text = (article.get('title', '') + ' ' + article.get('content', '')).lower()
            
            # Count sentiment words
            positive_count = sum(1 for w in positive_words if w in text)
            negative_count = sum(1 for w in negative_words if w in text)
            
            # Weight by keyword relevance
            keyword_matches = sum(1 for k in keywords if k.lower() in text)
            relevance = 0.5 + (keyword_matches / len(keywords)) * 0.5 if keywords else 0.5
            
            total_positive += positive_count * relevance
            total_negative += negative_count * relevance
            total_relevance += relevance
        
        # Calculate sentiment score
        total_sentiment = total_positive + total_negative
        if total_sentiment > 0:
            sentiment_score = (total_positive - total_negative) / total_sentiment
        else:
            sentiment_score = 0.0
        
        # Calculate confidence
        # Higher with more articles and more consistent sentiment
        article_factor = min(len(articles) / 10, 1.0)  # Max out at 10 articles
        consistency_factor = abs(sentiment_score)  # Strong sentiment = consistent
        confidence = 0.4 + (article_factor * 0.3) + (consistency_factor * 0.3)
        
        return sentiment_score, min(confidence, 0.95)
    
    def get_trade_recommendation(
        self,
        signal: SentimentSignal,
        current_price: float,
        bankroll: float
    ) -> Dict[str, Any]:
        """
        Get trade recommendation based on sentiment signal
        """
        if signal.signal == 'NEUTRAL' or signal.confidence < self.min_confidence:
            return {
                'action': 'HOLD',
                'reason': 'Insufficient signal strength or confidence'
            }
        
        # Determine trade direction
        if signal.signal == 'BULLISH':
            # Positive sentiment, buy YES if underpriced
            if current_price < 0.5 + (signal.sentiment_score * 0.3):
                action = 'BUY_YES'
                edge = signal.sentiment_score * 0.1  # Estimated edge
            else:
                return {'action': 'HOLD', 'reason': 'Price already reflects sentiment'}
        else:  # BEARISH
            # Negative sentiment, buy NO if underpriced
            if current_price > 0.5 + (signal.sentiment_score * 0.3):
                action = 'BUY_NO'
                edge = abs(signal.sentiment_score) * 0.1
            else:
                return {'action': 'HOLD', 'reason': 'Price already reflects sentiment'}
        
        # Size position based on confidence
        position_pct = 0.02 + (signal.confidence - 0.5) * 0.06  # 2-8% of bankroll
        position_size = min(position_pct * bankroll, bankroll * 0.10)
        
        return {
            'action': action,
            'market_id': signal.market_id,
            'size': round(position_size, 2),
            'price': current_price,
            'edge': edge,
            'confidence': signal.confidence,
            'sentiment': signal.sentiment_score,
            'article_count': signal.article_count,
            'keywords': signal.keywords,
        }
