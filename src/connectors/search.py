"""
Web Search Connector using Tavily API
Based on official Polymarket agents framework
"""
import os
import logging
from typing import List, Optional
from dataclasses import dataclass
import httpx

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """Web search result"""
    title: str
    url: str
    content: str
    score: float = 0.0
    
    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "url": self.url,
            "content": self.content,
            "score": self.score
        }
    
    def summary(self) -> str:
        """Get result summary for prompts"""
        return f"**{self.title}**\n{self.content[:500]}..."


class TavilySearchConnector:
    """
    Connector for Tavily AI-powered web search
    
    Tavily provides real-time web search optimized for AI applications
    
    Usage:
        connector = TavilySearchConnector()
        results = connector.search("Trump election odds 2024")
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Tavily connector
        
        Args:
            api_key: Tavily API key (or set TAVILY_API_KEY env var)
        """
        self.api_key = api_key or os.getenv("TAVILY_API_KEY", "")
        self.base_url = "https://api.tavily.com"
        
        if not self.api_key:
            logger.warning("Tavily API key not set - web search disabled")
    
    def search(
        self,
        query: str,
        search_depth: str = "basic",  # basic or advanced
        max_results: int = 5,
        include_domains: Optional[List[str]] = None,
        exclude_domains: Optional[List[str]] = None
    ) -> List[SearchResult]:
        """
        Search the web using Tavily
        
        Args:
            query: Search query
            search_depth: "basic" (faster) or "advanced" (more thorough)
            max_results: Maximum results to return
            include_domains: Only search these domains
            exclude_domains: Exclude these domains
            
        Returns:
            List of SearchResult objects
        """
        if not self.api_key:
            logger.warning("Tavily API key not configured")
            return []
        
        try:
            payload = {
                "api_key": self.api_key,
                "query": query,
                "search_depth": search_depth,
                "max_results": max_results,
                "include_answer": False,
                "include_raw_content": False
            }
            
            if include_domains:
                payload["include_domains"] = include_domains
            if exclude_domains:
                payload["exclude_domains"] = exclude_domains
            
            response = httpx.post(
                f"{self.base_url}/search",
                json=payload,
                timeout=30
            )
            
            if response.status_code != 200:
                logger.error(f"Tavily error: {response.status_code} - {response.text}")
                return []
            
            data = response.json()
            results = []
            
            for item in data.get("results", []):
                results.append(SearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    content=item.get("content", ""),
                    score=item.get("score", 0.0)
                ))
            
            return results
            
        except Exception as e:
            logger.error(f"Tavily search failed: {e}")
            return []
    
    def get_market_context(
        self,
        question: str,
        max_results: int = 5
    ) -> str:
        """
        Get web search context for a prediction market
        
        Args:
            question: Market question
            max_results: Max results to include
            
        Returns:
            Formatted search context string for prompts
        """
        results = self.search(
            query=question,
            search_depth="advanced",
            max_results=max_results,
            # Prefer authoritative sources
            include_domains=[
                "reuters.com", "apnews.com", "bbc.com", "nytimes.com",
                "wsj.com", "bloomberg.com", "politico.com", "538.com",
                "realclearpolitics.com", "predictit.org"
            ]
        )
        
        if not results:
            return "No web search results found for this market."
        
        context_parts = ["**Web Search Results:**\n"]
        for i, result in enumerate(results, 1):
            context_parts.append(f"{i}. {result.summary()}\n")
        
        return "\n".join(context_parts)


class DuckDuckGoSearchConnector:
    """
    Fallback search connector using DuckDuckGo (no API key needed)
    """
    
    def __init__(self):
        self.base_url = "https://api.duckduckgo.com"
    
    def search(self, query: str, max_results: int = 5) -> List[SearchResult]:
        """
        Search using DuckDuckGo instant answers
        
        Args:
            query: Search query
            max_results: Maximum results
            
        Returns:
            List of SearchResult objects
        """
        try:
            response = httpx.get(
                self.base_url,
                params={
                    "q": query,
                    "format": "json",
                    "no_html": 1,
                    "skip_disambig": 1
                },
                timeout=30
            )
            
            if response.status_code != 200:
                return []
            
            data = response.json()
            results = []
            
            # Abstract (main answer)
            if data.get("AbstractText"):
                results.append(SearchResult(
                    title=data.get("Heading", ""),
                    url=data.get("AbstractURL", ""),
                    content=data.get("AbstractText", ""),
                    score=1.0
                ))
            
            # Related topics
            for topic in data.get("RelatedTopics", [])[:max_results - 1]:
                if isinstance(topic, dict) and topic.get("Text"):
                    results.append(SearchResult(
                        title=topic.get("Text", "")[:100],
                        url=topic.get("FirstURL", ""),
                        content=topic.get("Text", ""),
                        score=0.8
                    ))
            
            return results[:max_results]
            
        except Exception as e:
            logger.error(f"DuckDuckGo search failed: {e}")
            return []
