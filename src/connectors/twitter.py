"""
Twitter/X Trending Topics Connector

Monitors trending topics on Twitter/X to validate news signals
and identify emerging narratives before they hit mainstream news.

Note: Requires Twitter API v2 access (Free tier may be limited)
"""
import os
import logging
from typing import List, Dict, Optional, Set
from dataclasses import dataclass
from datetime import datetime
import httpx

logger = logging.getLogger(__name__)


@dataclass
class Trend:
    """Twitter trending topic"""
    name: str
    url: str
    tweet_volume: Optional[int]
    rank: int


@dataclass
class Tweet:
    """Tweet data"""
    id: str
    text: str
    author_id: str
    created_at: str
    public_metrics: Dict
    

class TwitterConnector:
    """
    Connector for Twitter/X API v2
    
    Features:
    - Get trending topics by location
    - Search recent tweets by keyword
    - Monitor hashtags
    - Validate news signals with social sentiment
    
    Usage:
        connector = TwitterConnector()
        trends = connector.get_trending()
        tweets = connector.search("Trump election")
    """
    
    def __init__(self, bearer_token: Optional[str] = None):
        """
        Initialize Twitter connector
        
        Args:
            bearer_token: Twitter API Bearer Token (or set TWITTER_BEARER_TOKEN env var)
        """
        self.bearer_token = bearer_token or os.getenv("TWITTER_BEARER_TOKEN", "")
        self.base_url = "https://api.twitter.com/2"
        
        if not self.bearer_token:
            logger.warning("Twitter Bearer Token not set - Twitter features disabled")
    
    def _get_headers(self) -> Dict:
        """Get authentication headers"""
        return {
            "Authorization": f"Bearer {self.bearer_token}",
            "User-Agent": "PolymarketTradingBot/1.0"
        }
    
    def search_recent_tweets(
        self,
        query: str,
        max_results: int = 10,
        tweet_fields: Optional[List[str]] = None
    ) -> List[Tweet]:
        """
        Search recent tweets (last 7 days)
        
        Args:
            query: Search query (supports operators like AND, OR, hashtags, etc.)
            max_results: Max tweets to return (10-100)
            tweet_fields: Additional fields to include
            
        Returns:
            List of Tweet objects
        """
        if not self.bearer_token:
            logger.warning("Twitter API not configured")
            return []
        
        try:
            fields = tweet_fields or ["created_at", "public_metrics", "author_id"]
            
            response = httpx.get(
                f"{self.base_url}/tweets/search/recent",
                headers=self._get_headers(),
                params={
                    "query": query,
                    "max_results": min(max_results, 100),
                    "tweet.fields": ",".join(fields)
                },
                timeout=30
            )
            
            if response.status_code != 200:
                logger.error(f"Twitter API error: {response.status_code} - {response.text}")
                return []
            
            data = response.json()
            tweets = []
            
            for item in data.get("data", []):
                tweets.append(Tweet(
                    id=item.get("id", ""),
                    text=item.get("text", ""),
                    author_id=item.get("author_id", ""),
                    created_at=item.get("created_at", ""),
                    public_metrics=item.get("public_metrics", {})
                ))
            
            return tweets
            
        except Exception as e:
            logger.error(f"Twitter search failed: {e}")
            return []
    
    def get_trending_topics(self, woeid: int = 1) -> List[Trend]:
        """
        Get trending topics for a location
        
        Args:
            woeid: Where On Earth ID (1=Worldwide, 2459115=NYC, 2487956=SF, etc.)
            
        Returns:
            List of Trend objects
            
        Note: This endpoint requires Twitter API v1.1 
        """
        # Note: Twitter v2 API doesn't have a direct trends endpoint
        # Would need to use v1.1 API or scrape trending page
        # For now, return empty list with warning
        logger.warning("Trending topics endpoint not yet implemented for API v2")
        return []
    
    def check_keyword_trending(self, keywords: List[str]) -> Dict[str, float]:
        """
        Check if keywords are trending by searching recent tweets
        
        Returns dict mapping keyword to "trending score" (0-1)
        based on tweet volume in last hour
        """
        if not self.bearer_token:
            return {kw: 0.0 for kw in keywords}
        
        scores = {}
        
        for keyword in keywords:
            try:
                # Search for keyword
                tweets = self.search_recent_tweets(
                    query=f"{keyword} -is:retweet",
                    max_results=100
                )
                
                if not tweets:
                    scores[keyword] = 0.0
                    continue
                
                # Calculate score based on:
                # 1. Number of tweets
                # 2. Engagement (likes, retweets)
                # 3. Recency
                
                total_engagement = 0
                recent_count = 0
                now = datetime.utcnow()
                
                for tweet in tweets:
                    metrics = tweet.public_metrics
                    total_engagement += (
                        metrics.get("like_count", 0) +
                        metrics.get("retweet_count", 0) * 2 +
                        metrics.get("reply_count", 0)
                    )
                    
                    # Check if tweet is from last hour
                    try:
                        tweet_time = datetime.fromisoformat(tweet.created_at.replace('Z', '+00:00'))
                        if (now - tweet_time.replace(tzinfo=None)).total_seconds() < 3600:
                            recent_count += 1
                    except:
                        pass
                
                # Normalize score (0-1)
                volume_score = min(len(tweets) / 100, 1.0)
                engagement_score = min(total_engagement / 10000, 1.0)
                recency_score = min(recent_count / 50, 1.0)
                
                # Weighted average
                score = (volume_score * 0.4 + engagement_score * 0.4 + recency_score * 0.2)
                scores[keyword] = score
                
                logger.info(f"Twitter trending score for '{keyword}': {score:.2f}")
                
            except Exception as e:
                logger.error(f"Failed to check trending for '{keyword}': {e}")
                scores[keyword] = 0.0
        
        return scores
    
    def get_sentiment_for_query(self, query: str, max_results: int = 50) -> Dict[str, any]:
        """
        Analyze sentiment for a search query based on recent tweets
        
        Returns:
            Dict with sentiment analysis results
        """
        tweets = self.search_recent_tweets(query, max_results=max_results)
        
        if not tweets:
            return {
                'sentiment': 'neutral',
                'confidence': 0.0,
                'positive_count': 0,
                'negative_count': 0,
                'neutral_count': 0,
                'total_tweets': 0
            }
        
        # Simple sentiment analysis based on keywords
        positive_words = {'good', 'great', 'excellent', 'awesome', 'win', 'success', 'yes', 'positive', 'up', 'bullish'}
        negative_words = {'bad', 'terrible', 'awful', 'lose', 'failure', 'no', 'negative', 'down', 'bearish', 'crash'}
        
        positive_count = 0
        negative_count = 0
        neutral_count = 0
        
        for tweet in tweets:
            text_lower = tweet.text.lower()
            
            # Count sentiment words
            pos_matches = sum(1 for word in positive_words if word in text_lower)
            neg_matches = sum(1 for word in negative_words if word in text_lower)
            
            if pos_matches > neg_matches:
                positive_count += 1
            elif neg_matches > pos_matches:
                negative_count += 1
            else:
                neutral_count += 1
        
        total = len(tweets)
        
        # Determine overall sentiment
        if positive_count > negative_count * 1.5:
            sentiment = 'positive'
            confidence = positive_count / total
        elif negative_count > positive_count * 1.5:
            sentiment = 'negative'
            confidence = negative_count / total
        else:
            sentiment = 'neutral'
            confidence = neutral_count / total
        
        return {
            'sentiment': sentiment,
            'confidence': confidence,
            'positive_count': positive_count,
            'negative_count': negative_count,
            'neutral_count': neutral_count,
            'total_tweets': total,
            'sample_tweets': [t.text[:100] for t in tweets[:5]]
        }
    
    def monitor_hashtag(self, hashtag: str, minutes: int = 60) -> Dict:
        """
        Monitor hashtag activity over time period
        
        Returns metrics about hashtag usage
        """
        if not hashtag.startswith('#'):
            hashtag = f"#{hashtag}"
        
        tweets = self.search_recent_tweets(
            query=f"{hashtag} -is:retweet",
            max_results=100
        )
        
        if not tweets:
            return {
                'hashtag': hashtag,
                'active': False,
                'tweet_count': 0,
                'engagement': 0
            }
        
        # Calculate metrics
        total_engagement = sum(
            t.public_metrics.get("like_count", 0) +
            t.public_metrics.get("retweet_count", 0) * 2
            for t in tweets
        )
        
        return {
            'hashtag': hashtag,
            'active': True,
            'tweet_count': len(tweets),
            'engagement': total_engagement,
            'avg_engagement': total_engagement / len(tweets) if tweets else 0,
            'sample_tweets': [t.text[:100] for t in tweets[:3]]
        }


def validate_news_with_twitter(
    news_keywords: List[str],
    twitter_connector: TwitterConnector,
    boost_threshold: float = 0.5
) -> float:
    """
    Validate news signal with Twitter trending data
    
    Returns boost factor (1.0-1.5) based on Twitter activity
    """
    if not twitter_connector.bearer_token:
        return 1.0
    
    try:
        trending_scores = twitter_connector.check_keyword_trending(news_keywords)
        
        # Calculate average trending score
        if not trending_scores:
            return 1.0
        
        avg_score = sum(trending_scores.values()) / len(trending_scores)
        
        # If trending above threshold, boost confidence
        if avg_score >= boost_threshold:
            boost = 1.0 + (avg_score * 0.5)  # Up to 1.5x boost
            logger.info(f"Twitter validation boost: {boost:.2f}x (score: {avg_score:.2f})")
            return boost
        
        return 1.0
        
    except Exception as e:
        logger.error(f"Twitter validation failed: {e}")
        return 1.0
