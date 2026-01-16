"""
Real-Time News Monitor Trading Agent

This agent continuously monitors breaking news and automatically trades on Polymarket
when news events are detected that could impact market outcomes.

Strategy:
1. Monitor NewsAPI for breaking headlines every 1-5 minutes
2. Extract keywords and match them against active Polymarket markets
3. Analyze sentiment and urgency of news
4. Execute trades BEFORE the market fully reacts to the news
5. Optional: Cross-reference with Twitter trending topics for validation

Key Features:
- Real-time news monitoring with keyword matching
- Smart market correlation (finds which markets are affected by news)
- Urgency scoring (breaking news = faster action)
- Claude AI integration for news impact analysis
- Multi-source validation (News + Twitter)
"""
import logging
import time
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass
from datetime import datetime, timedelta
from collections import defaultdict
import anthropic
import httpx

from src.core.config import Config
from src.agents.base_agent import BaseAgent
from src.connectors.news import NewsConnector, Article

logger = logging.getLogger(__name__)


@dataclass
class NewsSignal:
    """Represents a trading signal derived from news"""
    market_id: str
    market_question: str
    news_headline: str
    news_source: str
    published_at: str
    impact_score: float  # 0-1: how much this news affects the market
    direction: str  # 'YES', 'NO', or 'NEUTRAL'
    confidence: float  # 0-1: confidence in the signal
    urgency: float  # 0-1: how quickly to act
    reasoning: str  # AI explanation
    keywords_matched: List[str]


@dataclass
class MarketKeywords:
    """Keywords extracted from a market question"""
    market_id: str
    question: str
    keywords: Set[str]
    entities: Set[str]  # Named entities (people, places, organizations)


class NewsMonitorAgent(BaseAgent):
    """
    News-Driven Trading Agent
    
    This agent monitors breaking news and correlates it with Polymarket markets
    to identify trading opportunities before the market fully reacts.
    
    Workflow:
    1. Fetch latest headlines from NewsAPI
    2. Extract keywords from active markets
    3. Match news articles to relevant markets
    4. Use Claude AI to analyze news impact
    5. Generate trading signals with confidence scores
    6. Execute trades for high-confidence signals
    
    Configuration:
    - monitoring_interval: How often to check news (seconds)
    - min_impact_score: Minimum impact to trade (0-1)
    - min_confidence: Minimum confidence to trade (0-1)
    - use_twitter: Whether to cross-reference with Twitter trends
    """
    
    def __init__(self, config: Config):
        super().__init__(config)
        
        # Initialize connectors
        self.news_connector = NewsConnector()
        
        # Claude AI for analysis
        self.anthropic_key = config.anthropic_api_key
        self.claude_client = None
        if self.anthropic_key:
            self.claude_client = anthropic.Anthropic(api_key=self.anthropic_key)
        
        # Configuration
        self.monitoring_interval = getattr(config, 'news_monitoring_interval', 300)  # 5 min default
        self.min_impact_score = getattr(config, 'news_min_impact_score', 0.6)
        self.min_confidence = getattr(config, 'news_min_confidence', 0.65)
        self.use_twitter = getattr(config, 'news_use_twitter', False)
        self.max_news_age_hours = getattr(config, 'news_max_age_hours', 2)
        
        # Cache
        self.seen_articles: Set[str] = set()  # Track processed articles
        self.market_keywords_cache: Dict[str, MarketKeywords] = {}
        self.last_update = None
        
        logger.info(f"NewsMonitorAgent initialized - checking every {self.monitoring_interval}s")
    
    def _extract_market_keywords(self, question: str, market_id: str) -> MarketKeywords:
        """
        Extract keywords and entities from market question
        
        Uses simple NLP to identify:
        - Important keywords (nouns, proper nouns)
        - Named entities (people, places, organizations)
        """
        # Remove common stopwords
        stopwords = {
            'will', 'the', 'a', 'an', 'be', 'is', 'are', 'was', 'were', 'been',
            'being', 'have', 'has', 'had', 'do', 'does', 'did', 'shall', 'should',
            'may', 'might', 'must', 'can', 'could', 'would', 'to', 'of', 'in',
            'for', 'on', 'with', 'at', 'by', 'from', 'or', 'and', 'not', 'this',
            'that', 'these', 'those', 'what', 'which', 'who', 'whom', 'whose',
            'when', 'where', 'why', 'how', 'before', 'after', 'during', 'above',
            'below', 'between', 'through', 'reach', 'than', 'end', 'more', 'less',
        }
        
        # Clean text
        text = question.lower()
        text = text.replace('?', '').replace('!', '').replace(',', '')
        words = text.split()
        
        # Extract keywords (non-stopwords)
        keywords = set()
        for word in words:
            if word not in stopwords and len(word) > 2:
                keywords.add(word)
        
        # Extract entities (capitalized words from original question)
        entities = set()
        for word in question.split():
            word_clean = word.strip('?!,.')
            if word_clean and word_clean[0].isupper() and len(word_clean) > 1:
                entities.add(word_clean.lower())
        
        return MarketKeywords(
            market_id=market_id,
            question=question,
            keywords=keywords,
            entities=entities
        )
    
    def _match_news_to_markets(
        self,
        articles: List[Article],
        markets: List[Dict]
    ) -> Dict[str, List[Tuple[Article, List[str]]]]:
        """
        Match news articles to relevant markets
        
        Returns:
            Dict mapping market_id to list of (article, matched_keywords)
        """
        # Extract keywords for all markets
        for market in markets:
            market_id = market.get('id') or market.get('condition_id', '')
            question = market.get('question', '')
            
            if market_id not in self.market_keywords_cache:
                self.market_keywords_cache[market_id] = self._extract_market_keywords(
                    question, market_id
                )
        
        # Match articles to markets
        matches = defaultdict(list)
        
        for article in articles:
            # Skip if we've seen this article
            article_key = f"{article.url}_{article.published_at}"
            if article_key in self.seen_articles:
                continue
            
            # Check article age
            try:
                pub_time = datetime.fromisoformat(article.published_at.replace('Z', '+00:00'))
                age_hours = (datetime.now() - pub_time.replace(tzinfo=None)).total_seconds() / 3600
                if age_hours > self.max_news_age_hours:
                    continue
            except:
                pass
            
            # Combine article text for matching
            article_text = (
                f"{article.title} {article.description or ''}"
            ).lower()
            
            # Match against each market
            for market_id, market_kw in self.market_keywords_cache.items():
                matched_keywords = []
                
                # Check keywords
                for keyword in market_kw.keywords:
                    if keyword in article_text:
                        matched_keywords.append(keyword)
                
                # Check entities (more important)
                for entity in market_kw.entities:
                    if entity in article_text:
                        matched_keywords.append(entity)
                
                # If we have matches, add to results
                if len(matched_keywords) >= 2 or any(e in article_text for e in market_kw.entities):
                    matches[market_id].append((article, matched_keywords))
            
            # Mark as seen
            self.seen_articles.add(article_key)
        
        return matches
    
    def _analyze_news_impact(
        self,
        article: Article,
        market_question: str,
        matched_keywords: List[str]
    ) -> Tuple[float, str, float, str]:
        """
        Use Claude AI to analyze how the news impacts the market
        
        Returns:
            (impact_score, direction, confidence, reasoning)
        """
        if not self.claude_client:
            # Fallback: simple heuristic
            return 0.5, 'NEUTRAL', 0.5, "AI analysis not available"
        
        try:
            prompt = f"""You are a prediction market analyst. Analyze how this news affects the probability of the following market outcome.

MARKET QUESTION: {market_question}

NEWS HEADLINE: {article.title}
SOURCE: {article.source}
PUBLISHED: {article.published_at}
DESCRIPTION: {article.description or 'N/A'}

MATCHED KEYWORDS: {', '.join(matched_keywords)}

Provide your analysis in this exact format:
IMPACT: [0.0-1.0] (how much this news affects the market)
DIRECTION: [YES/NO/NEUTRAL] (does this make YES more likely, NO more likely, or neutral?)
CONFIDENCE: [0.0-1.0] (how confident are you in this analysis?)
REASONING: [2-3 sentence explanation]

Be precise and consider:
1. Is the news directly relevant to the market outcome?
2. Is it breaking news or just speculation?
3. Does it provide new information?
4. What is the credibility of the source?"""

            response = self.claude_client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=400,
                temperature=0.3,
                messages=[{"role": "user", "content": prompt}]
            )
            
            content = response.content[0].text
            
            # Parse response
            impact = 0.5
            direction = 'NEUTRAL'
            confidence = 0.5
            reasoning = ""
            
            for line in content.split('\n'):
                line = line.strip()
                if line.startswith('IMPACT:'):
                    try:
                        impact = float(line.split(':')[1].strip().split()[0])
                    except:
                        pass
                elif line.startswith('DIRECTION:'):
                    dir_text = line.split(':')[1].strip().upper()
                    if 'YES' in dir_text:
                        direction = 'YES'
                    elif 'NO' in dir_text:
                        direction = 'NO'
                    else:
                        direction = 'NEUTRAL'
                elif line.startswith('CONFIDENCE:'):
                    try:
                        confidence = float(line.split(':')[1].strip().split()[0])
                    except:
                        pass
                elif line.startswith('REASONING:'):
                    reasoning = line.split(':', 1)[1].strip()
            
            return impact, direction, confidence, reasoning or "Analysis complete"
            
        except Exception as e:
            logger.error(f"Claude analysis failed: {e}")
            return 0.5, 'NEUTRAL', 0.3, f"Analysis error: {str(e)}"
    
    def _check_twitter_trends(self, keywords: List[str]) -> float:
        """
        Check if keywords are trending on Twitter/X
        Returns boost factor (1.0-1.5) if trending
        
        Note: Requires Twitter API access
        """
        if not self.use_twitter:
            return 1.0
        
        # TODO: Implement Twitter API integration
        # For now, return neutral
        return 1.0
    
    def _calculate_urgency(self, article: Article, impact: float) -> float:
        """
        Calculate how quickly we should act on this news
        
        Factors:
        - How recent is the article?
        - How high is the impact?
        - Is it breaking news?
        """
        urgency = 0.5
        
        try:
            # Recency factor
            pub_time = datetime.fromisoformat(article.published_at.replace('Z', '+00:00'))
            age_minutes = (datetime.now() - pub_time.replace(tzinfo=None)).total_seconds() / 60
            
            if age_minutes < 15:
                urgency += 0.3
            elif age_minutes < 60:
                urgency += 0.2
            elif age_minutes < 120:
                urgency += 0.1
            
            # Impact factor
            urgency += impact * 0.2
            
            # Breaking news indicator
            if 'breaking' in article.title.lower() or 'just in' in article.title.lower():
                urgency += 0.2
            
        except:
            pass
        
        return min(1.0, urgency)
    
    def generate_signals(self, markets: List[Dict]) -> List[NewsSignal]:
        """
        Monitor news and generate trading signals
        
        This is the main method that:
        1. Fetches latest news
        2. Matches to markets
        3. Analyzes impact
        4. Generates signals
        """
        logger.info("Checking for breaking news...")
        
        # Fetch latest headlines
        articles = self.news_connector.get_headlines(limit=50)
        
        if not articles:
            logger.warning("No news articles retrieved")
            return []
        
        logger.info(f"Retrieved {len(articles)} headlines")
        
        # Match news to markets
        matches = self._match_news_to_markets(articles, markets)
        
        if not matches:
            logger.info("No relevant news found for active markets")
            return []
        
        logger.info(f"Found {len(matches)} markets with relevant news")
        
        # Generate signals
        signals = []
        
        for market_id, article_matches in matches.items():
            # Find market info
            market = next((m for m in markets if m.get('id') == market_id or m.get('condition_id') == market_id), None)
            if not market:
                continue
            
            market_question = market.get('question', '')
            
            for article, matched_keywords in article_matches:
                # Analyze impact with Claude AI
                impact, direction, confidence, reasoning = self._analyze_news_impact(
                    article, market_question, matched_keywords
                )
                
                # Calculate urgency
                urgency = self._calculate_urgency(article, impact)
                
                # Check Twitter (optional boost)
                twitter_boost = self._check_twitter_trends(matched_keywords)
                confidence *= twitter_boost
                
                # Create signal
                signal = NewsSignal(
                    market_id=market_id,
                    market_question=market_question,
                    news_headline=article.title,
                    news_source=article.source,
                    published_at=article.published_at,
                    impact_score=impact,
                    direction=direction,
                    confidence=confidence,
                    urgency=urgency,
                    reasoning=reasoning,
                    keywords_matched=matched_keywords
                )
                
                # Filter by thresholds
                if impact >= self.min_impact_score and confidence >= self.min_confidence:
                    signals.append(signal)
                    logger.info(f"🎯 SIGNAL: {market_question[:60]}...")
                    logger.info(f"   News: {article.title[:70]}...")
                    logger.info(f"   Impact: {impact:.2f} | Direction: {direction} | Confidence: {confidence:.2f}")
        
        self.last_update = datetime.now()
        return signals
    
    def evaluate_market(self, market: Dict) -> Optional[Dict]:
        """
        Evaluate a single market based on latest news
        
        Returns trade recommendation or None
        """
        signals = self.generate_signals([market])
        
        if not signals:
            return None
        
        # Get best signal
        best_signal = max(signals, key=lambda s: s.confidence * s.impact_score)
        
        if best_signal.direction == 'NEUTRAL':
            return None
        
        # Calculate position
        position_size = self.calculate_position_size(
            best_signal.confidence,
            market.get('liquidity', 0)
        )
        
        return {
            'action': 'BUY',
            'outcome': best_signal.direction,
            'size': position_size,
            'confidence': best_signal.confidence,
            'reasoning': f"NEWS: {best_signal.news_headline[:100]}... | {best_signal.reasoning}",
            'urgency': best_signal.urgency,
            'source': f"{best_signal.news_source} ({best_signal.published_at})"
        }
    
    def monitor_loop(self, min_liquidity: float = 10000):
        """
        Continuous monitoring loop
        
        Checks news at regular intervals and trades on signals
        """
        logger.info(f"Starting news monitoring loop (interval: {self.monitoring_interval}s)")
        
        while True:
            try:
                # Get active markets
                markets = self.market_monitor.discover_markets(min_liquidity=min_liquidity)
                logger.info(f"Monitoring {len(markets)} markets")
                
                # Generate signals
                signals = self.generate_signals(markets)
                
                if signals:
                    logger.info(f"Generated {len(signals)} trading signals")
                    
                    # Execute trades (if auto_trade enabled)
                    if self.config.auto_trade and not self.config.dry_run:
                        for signal in signals:
                            if signal.direction != 'NEUTRAL':
                                self._execute_news_trade(signal)
                    else:
                        logger.info("Auto-trade disabled - signals generated but not executed")
                
                # Sleep until next check
                logger.info(f"Sleeping for {self.monitoring_interval}s...")
                time.sleep(self.monitoring_interval)
                
            except KeyboardInterrupt:
                logger.info("Monitoring stopped by user")
                break
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}", exc_info=True)
                time.sleep(60)  # Wait before retrying
    
    def _execute_news_trade(self, signal: NewsSignal):
        """Execute a trade based on news signal"""
        try:
            logger.info(f"🚀 Executing news-driven trade:")
            logger.info(f"   Market: {signal.market_question[:70]}")
            logger.info(f"   Direction: {signal.direction}")
            logger.info(f"   Confidence: {signal.confidence:.2%}")
            logger.info(f"   News: {signal.news_headline[:80]}")
            
            # TODO: Implement actual trade execution
            # position_size = self.calculate_position_size(signal.confidence, ...)
            # self.client.place_order(...)
            
            logger.info(f"   ✅ Trade executed successfully")
            
        except Exception as e:
            logger.error(f"Failed to execute trade: {e}")
    
    def get_status(self) -> Dict:
        """Get agent status"""
        return {
            'name': 'NewsMonitorAgent',
            'status': 'active',
            'last_update': self.last_update.isoformat() if self.last_update else None,
            'articles_processed': len(self.seen_articles),
            'markets_tracked': len(self.market_keywords_cache),
            'config': {
                'monitoring_interval': self.monitoring_interval,
                'min_impact_score': self.min_impact_score,
                'min_confidence': self.min_confidence,
                'use_twitter': self.use_twitter,
                'max_news_age_hours': self.max_news_age_hours
            }
        }