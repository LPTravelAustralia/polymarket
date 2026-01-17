#!/usr/bin/env python3
"""
Test script for API connections
Tests NewsAPI, Tavily, and other external API dependencies
"""

import os
import sys
import json
from typing import Dict, Any
from datetime import datetime, timedelta

# Color codes for terminal output
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def print_header(text):
    print(f"\n{Colors.BOLD}{Colors.HEADER}{'='*60}")
    print(f"{text}")
    print(f"{'='*60}{Colors.ENDC}\n")

def print_success(text):
    print(f"{Colors.OKGREEN}✓ {text}{Colors.ENDC}")

def print_error(text):
    print(f"{Colors.FAIL}✗ {text}{Colors.ENDC}")

def print_warning(text):
    print(f"{Colors.WARNING}⚠ {text}{Colors.ENDC}")

def print_info(text):
    print(f"{Colors.OKCYAN}ℹ {text}{Colors.ENDC}")

def test_newsapi():
    """Test NewsAPI connection"""
    print_header("Testing NewsAPI Connection")
    
    api_key = os.getenv("NEWSAPI_KEY", "").strip()
    
    if not api_key:
        print_error("NEWSAPI_KEY environment variable not set")
        return False
    
    if api_key == "your_newsapi_key_here" or api_key.startswith("sk-") == False:
        print_warning(f"NEWSAPI_KEY appears to be a placeholder: {api_key[:20]}...")
        return False
    
    try:
        import httpx
        print_info(f"Using API key: {api_key[:10]}...{api_key[-10:]}")
        
        async def fetch():
            async with httpx.AsyncClient(timeout=10) as client:
                # Test with a simple query
                params = {
                    "q": "Trump election",
                    "sortBy": "publishedAt",
                    "language": "en",
                    "apiKey": api_key,
                    "pageSize": 5
                }
                resp = await client.get(
                    "https://newsapi.org/v2/everything",
                    params=params
                )
                return resp
        
        import asyncio
        response = asyncio.run(fetch())
        
        if response.status_code == 200:
            data = response.json()
            article_count = len(data.get("articles", []))
            print_success(f"NewsAPI connection successful - retrieved {article_count} articles")
            if article_count > 0:
                first_article = data["articles"][0]
                print_info(f"Sample: {first_article.get('title', 'N/A')[:60]}...")
            return True
        elif response.status_code == 401:
            print_error(f"NewsAPI authentication failed (401) - Invalid API key")
            return False
        else:
            print_error(f"NewsAPI request failed with status {response.status_code}")
            print_info(f"Response: {response.text[:200]}")
            return False
            
    except Exception as e:
        print_error(f"NewsAPI test failed: {str(e)}")
        return False

def test_tavily():
    """Test Tavily API connection"""
    print_header("Testing Tavily API Connection")
    
    api_key = os.getenv("TAVILY_API_KEY", "").strip()
    
    if not api_key:
        print_error("TAVILY_API_KEY environment variable not set")
        return False
    
    if api_key == "your_tavily_api_key_here":
        print_warning(f"TAVILY_API_KEY appears to be a placeholder: {api_key}")
        return False
    
    try:
        import httpx
        print_info(f"Using API key: {api_key[:10]}...{api_key[-10:]}")
        
        async def fetch():
            async with httpx.AsyncClient(timeout=10) as client:
                payload = {
                    "api_key": api_key,
                    "query": "Trump election prediction market",
                    "include_answer": True,
                    "num_results": 3
                }
                resp = await client.post(
                    "https://api.tavily.com/search",
                    json=payload,
                    timeout=10
                )
                return resp
        
        import asyncio
        response = asyncio.run(fetch())
        
        if response.status_code == 200:
            data = response.json()
            result_count = len(data.get("results", []))
            print_success(f"Tavily API connection successful - retrieved {result_count} results")
            if result_count > 0:
                first_result = data["results"][0]
                print_info(f"Sample: {first_result.get('title', 'N/A')[:60]}...")
            return True
        elif response.status_code == 401:
            print_error(f"Tavily authentication failed (401) - Invalid API key")
            return False
        else:
            print_error(f"Tavily request failed with status {response.status_code}")
            print_info(f"Response: {response.text[:200]}")
            return False
            
    except Exception as e:
        print_error(f"Tavily test failed: {str(e)}")
        return False

def test_gamma_api():
    """Test Gamma API connection (local, no key needed)"""
    print_header("Testing Gamma API Connection (Polymarket)")
    
    try:
        import httpx
        
        async def fetch():
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://gamma-api.polymarket.com/markets",
                    params={"limit": 1}
                )
                return resp
        
        import asyncio
        response = asyncio.run(fetch())
        
        if response.status_code == 200:
            data = response.json()
            # Gamma API returns list directly
            market_count = len(data) if isinstance(data, list) else len(data.get("data", []))
            print_success(f"Gamma API connection successful - retrieved {market_count} markets")
            return True
        else:
            print_error(f"Gamma API request failed with status {response.status_code}")
            return False
            
    except Exception as e:
        print_error(f"Gamma API test failed: {str(e)}")
        return False

def test_anthropic():
    """Test Anthropic/Claude API connection"""
    print_header("Testing Anthropic (Claude) API Connection")
    
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    
    if not api_key:
        print_error("ANTHROPIC_API_KEY environment variable not set")
        return False
    
    if api_key == "your_anthropic_api_key_here" or len(api_key) < 10:
        print_warning(f"ANTHROPIC_API_KEY appears to be a placeholder")
        return False
    
    try:
        from anthropic import Anthropic
        print_info(f"Using API key: {api_key[:10]}...{api_key[-10:]}")
        
        client = Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-opus-4-1-20250805",
            max_tokens=100,
            messages=[
                {"role": "user", "content": "Say 'API test successful' in one sentence."}
            ]
        )
        
        response_text = message.content[0].text
        print_success(f"Anthropic API connection successful")
        print_info(f"Response: {response_text}")
        return True
        
    except Exception as e:
        print_error(f"Anthropic API test failed: {str(e)}")
        return False

def test_openai():
    """Test OpenAI API connection (fallback)"""
    print_header("Testing OpenAI API Connection (Fallback)")
    
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    
    if not api_key:
        print_warning("OPENAI_API_KEY environment variable not set (optional fallback)")
        return None
    
    if api_key == "your_openai_api_key_here" or len(api_key) < 10:
        print_warning(f"OPENAI_API_KEY appears to be a placeholder")
        return None
    
    try:
        from openai import OpenAI
        print_info(f"Using API key: {api_key[:10]}...{api_key[-10:]}")
        
        client = OpenAI(api_key=api_key)
        message = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=100,
            messages=[
                {"role": "user", "content": "Say 'API test successful' in one sentence."}
            ]
        )
        
        response_text = message.choices[0].message.content
        print_success(f"OpenAI API connection successful")
        print_info(f"Response: {response_text}")
        return True
        
    except Exception as e:
        print_error(f"OpenAI API test failed: {str(e)}")
        return False

def main():
    print(f"\n{Colors.BOLD}{Colors.HEADER}")
    print("╔════════════════════════════════════════════════════════╗")
    print("║     Polymarket Trading Bot - API Connection Tests      ║")
    print(f"║     {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}                              ║")
    print("╚════════════════════════════════════════════════════════╝")
    print(f"{Colors.ENDC}")
    
    results = {}
    
    # Test all APIs
    results['gamma'] = test_gamma_api()
    results['anthropic'] = test_anthropic()
    results['openai'] = test_openai()
    results['newsapi'] = test_newsapi()
    results['tavily'] = test_tavily()
    
    # Summary
    print_header("Test Summary")
    
    passed = sum(1 for v in results.values() if v is True)
    failed = sum(1 for v in results.values() if v is False)
    skipped = sum(1 for v in results.values() if v is None)
    total = len(results)
    
    for api, result in results.items():
        if result is True:
            print_success(f"{api.upper()}: PASSED")
        elif result is False:
            print_error(f"{api.upper()}: FAILED")
        else:
            print_warning(f"{api.upper()}: SKIPPED")
    
    print(f"\n{Colors.BOLD}")
    print(f"Results: {Colors.OKGREEN}{passed} passed{Colors.ENDC}, {Colors.FAIL}{failed} failed{Colors.ENDC}, {Colors.WARNING}{skipped} skipped{Colors.ENDC}")
    print(f"{Colors.ENDC}")
    
    if failed > 0:
        print_error("\nSome API tests failed. Check your API keys in the .env file.")
        sys.exit(1)
    else:
        print_success("\nAll critical APIs are connected!")
        sys.exit(0)

if __name__ == "__main__":
    main()
