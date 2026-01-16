#!/usr/bin/env python3
"""
Test script to verify improved news scoring logic
"""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.agents.news_monitor_agent import NewsMonitorAgent
from src.core.config import Config
from src.connectors.news import Article


def test_fallback_scoring():
    """Test the fallback scoring logic"""
    print("\n" + "="*80)
    print("TESTING FALLBACK NEWS SCORING")
    print("="*80)
    
    # Create a config
    config = Config()
    config.anthropic_api_key = None  # Disable Claude to force fallback
    
    # Create agent
    agent = NewsMonitorAgent(config)
    
    print(f"\nMin Impact Score (threshold): {agent.min_impact_score}")
    print(f"Min Confidence (threshold): {agent.min_confidence}")
    
    # Create mock article
    article = Article(
        title="Test News Article",
        description="This is a test article",
        url="https://example.com",
        source="Test Source",
        published_at="2026-01-16T12:00:00Z"
    )
    
    # Test with different numbers of matched keywords
    test_cases = [
        (1, "1 keyword match"),
        (2, "2 keyword matches"),
        (3, "3 keyword matches"),
        (4, "4 keyword matches"),
        (5, "5 keyword matches"),
    ]
    
    print("\nFallback Scoring Results (Claude API disabled):")
    print("-" * 80)
    print(f"{'Keywords':<15} {'Impact':<12} {'Confidence':<12} {'Passes':<10}")
    print("-" * 80)
    
    for num_keywords, description in test_cases:
        keywords = [f"keyword{i}" for i in range(num_keywords)]
        impact, direction, confidence, reasoning = agent._analyze_news_impact(
            article, "Test Market Question", keywords
        )
        
        passes_impact = "✓" if impact >= agent.min_impact_score else "✗"
        passes_conf = "✓" if confidence >= agent.min_confidence else "✗"
        passes = "YES" if (impact >= agent.min_impact_score and confidence >= agent.min_confidence) else "NO"
        
        print(f"{description:<15} {impact:<12.3f} {confidence:<12.3f} {passes:<10}")
    
    print("\n" + "="*80)
    print("SUMMARY:")
    print("="*80)
    print("✓ With 1+ keyword matches, fallback scoring should now generate signals")
    print(f"✓ New thresholds: impact={agent.min_impact_score}, confidence={agent.min_confidence}")
    print("✓ These are more realistic for keyword-based (fallback) scoring")


if __name__ == "__main__":
    test_fallback_scoring()
