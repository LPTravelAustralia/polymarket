"""
NewsAPI Connector for fetching relevant news articles
Based on official Polymarket agents framework
"""
import os
import logging
from typing import List, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta
import httpx

logger = logging.getLogger(__name__)


@dataclass
class Article:
    """News article data"""
    title: str
    description: str
    url: str
    source: str
    published_at: str
    content: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "description": self.description,
            "url": self.url,
            "source": self.source,
            "published_at": self.published_at,
            "content": self.content
        }
    
    def summary(self) -> str:
        """Get article summary for prompts"""
        return f"**{self.title}** ({self.source}, {self.published_at})\n{self.description or ''}"


class NewsConnector:
    """
    Connector for NewsAPI to fetch relevant news articles
    
    Usage:
        connector = NewsConnector()
        articles = connector.search("Trump election 2024")
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize NewsAPI connector
        
        Args:
            api_key: NewsAPI key (or set NEWSAPI_KEY env var)
        """
        self.api_key = api_key or os.getenv("NEWSAPI_KEY", "")
        self.base_url = "https://newsapi.org/v2"
        
        if not self.api_key:
            logger.warning("NewsAPI key not set - news features disabled")
    
    def search(
        self,
        query: str,
        days_back: int = 7,
        limit: int = 10,
        language: str = "en",
        sort_by: str = "relevancy"
    ) -> List[Article]:
        """
        Search for news articles
        
        Args:
            query: Search query
            days_back: How many days back to search
            limit: Maximum articles to return
            language: Article language
            sort_by: Sort order (relevancy, popularity, publishedAt)
            
        Returns:
            List of Article objects
        """
        if not self.api_key:
            logger.warning("NewsAPI key not configured")
            return []
        
        try:
            from_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
            
            response = httpx.get(
                f"{self.base_url}/everything",
                params={
                    "q": query,
                    "from": from_date,
                    "language": language,
                    "sortBy": sort_by,
                    "pageSize": limit,
                    "apiKey": self.api_key
                },
                timeout=30
            )
            
            if response.status_code != 200:
                logger.error(f"NewsAPI error: {response.status_code} - {response.text}")
                return []
            
            data = response.json()
            articles = []
            
            for item in data.get("articles", []):
                articles.append(Article(
                    title=item.get("title", ""),
                    description=item.get("description", ""),
                    url=item.get("url", ""),
                    source=item.get("source", {}).get("name", "Unknown"),
                    published_at=item.get("publishedAt", ""),
                    content=item.get("content")
                ))
            
            return articles
            
        except Exception as e:
            logger.error(f"NewsAPI search failed: {e}")
            return []
    
    def get_headlines(
        self,
        category: Optional[str] = None,
        country: str = "us",
        limit: int = 10
    ) -> List[Article]:
        """
        Get top headlines
        
        Args:
            category: Category (business, entertainment, general, health, science, sports, technology)
            country: Country code
            limit: Maximum articles
            
        Returns:
            List of Article objects
        """
        if not self.api_key:
            return []
        
        try:
            params = {
                "country": country,
                "pageSize": limit,
                "apiKey": self.api_key
            }
            if category:
                params["category"] = category
            
            response = httpx.get(
                f"{self.base_url}/top-headlines",
                params=params,
                timeout=30
            )
            
            if response.status_code != 200:
                return []
            
            data = response.json()
            articles = []
            
            for item in data.get("articles", []):
                articles.append(Article(
                    title=item.get("title", ""),
                    description=item.get("description", ""),
                    url=item.get("url", ""),
                    source=item.get("source", {}).get("name", "Unknown"),
                    published_at=item.get("publishedAt", "")
                ))
            
            return articles
            
        except Exception as e:
            logger.error(f"NewsAPI headlines failed: {e}")
            return []
    
    def get_market_context(
        self,
        question: str,
        description: Optional[str] = None,
        limit: int = 5
    ) -> str:
        """
        Get news context for a prediction market
        
        Args:
            question: Market question
            description: Optional market description
            limit: Max articles to include
            
        Returns:
            Formatted news context string for prompts
        """
        # Extract key terms from question for search
        # Remove common words and punctuation
        stop_words = {"will", "the", "a", "an", "be", "by", "in", "on", "to", "for", "of", "is", "are", "?", "!"}
        words = question.lower().replace("?", "").replace("!", "").split()
        keywords = [w for w in words if w not in stop_words and len(w) > 2]
        
        # Search with first few keywords
        query = " ".join(keywords[:5])
        articles = self.search(query, days_back=7, limit=limit)
        
        if not articles:
            return "No recent news articles found for this market."
        
        context_parts = ["**Recent News:**\n"]
        for i, article in enumerate(articles, 1):
            context_parts.append(f"{i}. {article.summary()}\n")
        
        return "\n".join(context_parts)
