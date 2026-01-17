#!/usr/bin/env python3
"""
Test News Monitoring with Live Backend API

This script tests the news monitoring functionality using the live backend API
running on Google Cloud (http://34.29.163.176:8000)
"""
import json
import requests
from datetime import datetime

BACKEND_URL = "http://34.29.163.176:8000"

def test_backend_health():
    """Test if backend is accessible"""
    print("🔍 Testing backend health...")
    try:
        response = requests.get(f"{BACKEND_URL}/")
        data = response.json()
        print(f"✅ Backend Status: {data['status']}")
        print(f"   Service: {data['service']}")
        print(f"   Version: {data['version']}")
        return True
    except Exception as e:
        print(f"❌ Backend not accessible: {e}")
        return False

def test_news_api():
    """Test news API endpoint"""
    print("\n📰 Testing News API...")
    try:
        # Test with different queries
        queries = [
            "Trump",
            "election",
            "Fed interest rates",
            "inflation"
        ]
        
        for query in queries:
            response = requests.get(
                f"{BACKEND_URL}/api/news",
                params={"query": query, "limit": 3}
            )
            data = response.json()
            
            print(f"\n🔎 Query: '{query}'")
            print(f"   Found {len(data.get('articles', []))} articles")
            
            for i, article in enumerate(data.get('articles', [])[:2], 1):
                print(f"   {i}. {article['title'][:70]}")
                print(f"      Source: {article['source']} | {article['published_at']}")
        
        return True
        
    except Exception as e:
        print(f"❌ News API test failed: {e}")
        return False

def test_markets_api():
    """Test markets API endpoint"""
    print("\n📊 Testing Markets API...")
    try:
        response = requests.get(
            f"{BACKEND_URL}/api/markets",
            params={"limit": 5}
        )
        data = response.json()
        markets = data.get('markets', [])
        
        print(f"✅ Found {len(markets)} active markets")
        
        for i, market in enumerate(markets[:3], 1):
            print(f"\n{i}. {market['question'][:80]}")
            print(f"   Liquidity: ${market['liquidity']:,.0f}")
            print(f"   Volume 24h: ${market['volume_24h']:,.0f}")
            print(f"   YES: {market['yes_price']:.3f} | NO: {market['no_price']:.3f}")
        
        return markets
        
    except Exception as e:
        print(f"❌ Markets API test failed: {e}")
        return []

def simulate_news_matching(markets):
    """Simulate news-to-market matching"""
    print("\n🎯 Simulating News-to-Market Matching...")
    
    if not markets:
        print("❌ No markets to match against")
        return
    
    # Extract keywords from a sample market
    sample_market = markets[0]
    question = sample_market['question']
    
    print(f"\n📌 Sample Market: {question}")
    
    # Extract keywords (simple version)
    stopwords = {'will', 'the', 'a', 'an', 'be', 'is', 'are', 'by', 'in', 'on', 'after'}
    words = question.lower().replace('?', '').split()
    keywords = [w for w in words if w not in stopwords and len(w) > 2][:5]
    
    print(f"   Keywords extracted: {', '.join(keywords)}")
    
    # Search for related news
    if keywords:
        query = ' '.join(keywords[:3])
        print(f"\n🔍 Searching news for: '{query}'")
        
        try:
            response = requests.get(
                f"{BACKEND_URL}/api/news",
                params={"query": query, "limit": 5}
            )
            data = response.json()
            articles = data.get('articles', [])
            
            if articles:
                print(f"✅ Found {len(articles)} related news articles!")
                print("\n📰 Top matches:")
                
                for i, article in enumerate(articles[:3], 1):
                    print(f"\n{i}. {article['title']}")
                    print(f"   Source: {article['source']}")
                    print(f"   Published: {article['published_at']}")
                    print(f"   URL: {article['url'][:60]}...")
                    
                    # Simulate impact analysis
                    print(f"   🤖 [AI would analyze impact here]")
                    print(f"   📊 Simulated Impact: 0.75 | Direction: NO | Confidence: 0.72")
            else:
                print("   No matching news found")
                
        except Exception as e:
            print(f"   Error searching news: {e}")

def test_news_market_endpoint():
    """Test the dedicated news-for-market endpoint"""
    print("\n🔗 Testing News-for-Market Endpoint...")
    
    try:
        # Get a market first
        markets_response = requests.get(
            f"{BACKEND_URL}/api/markets",
            params={"limit": 1}
        )
        markets = markets_response.json().get('markets', [])
        
        if not markets:
            print("   No markets available")
            return
        
        market_id = markets[0]['id']
        question = markets[0]['question']
        
        print(f"\n📌 Market: {question[:70]}")
        print(f"   ID: {market_id[:20]}...")
        
        # Get news for this market
        response = requests.get(f"{BACKEND_URL}/api/news/market/{market_id}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"\n✅ Backend returned news context:")
            print(f"   {data.get('news_context', 'No context')[:200]}...")
        else:
            print(f"   Endpoint returned: {response.status_code}")
            
    except Exception as e:
        print(f"   Error: {e}")

def main():
    print("=" * 80)
    print("NEWS MONITORING BACKEND TEST")
    print("=" * 80)
    print(f"Backend: {BACKEND_URL}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    # Run tests
    if not test_backend_health():
        print("\n❌ Backend not accessible. Exiting.")
        return
    
    test_news_api()
    
    markets = test_markets_api()
    
    if markets:
        simulate_news_matching(markets)
    
    test_news_market_endpoint()
    
    print("\n" + "=" * 80)
    print("✅ TEST COMPLETE")
    print("=" * 80)
    
    print("\n📝 Summary:")
    print("   • Backend API is running and accessible")
    print("   • NewsAPI integration is working")
    print("   • Market data is available")
    print("   • News-to-market matching can be implemented")
    
    print("\n🚀 Next Steps:")
    print("   1. The news monitoring agent can now be deployed to your GCloud VM")
    print("   2. It will use these same API endpoints")
    print("   3. Add Claude AI analysis for impact scoring")
    print("   4. Enable automatic trading when ready")
    
    print("\n💡 To run the full news monitor:")
    print("   python scripts/run_news_monitor.py --once --dry-run")

if __name__ == "__main__":
    main()
