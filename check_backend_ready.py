#!/usr/bin/env python3
"""Check if backend is fully configured and ready for news trading"""
import httpx
import sys

BACKEND_URL = "http://localhost:8000"

def check_backend():
    print("Checking backend configuration...")
    print("=" * 60)
    
    try:
        resp = httpx.get(f"{BACKEND_URL}/api/health", timeout=10)
        health = resp.json()
        
        markets = health.get('markets_cache_size', 0)
        anthropic = health.get('anthropic_key_loaded')
        
        print(f"✓ Backend is running")
        print(f"  Markets cached: {markets}")
        print(f"  Anthropic API key: {anthropic}")
        
        if not anthropic:
            print("\n❌ ANTHROPIC_API_KEY not loaded!")
            print("   Fix: Add to .env and restart backend")
            print("   export ANTHROPIC_API_KEY=sk-ant-...")
            print("   pkill -f uvicorn")
            print("   nohup uvicorn main:app --host 0.0.0.0 --port 8000 &")
            return False
        
        if markets == 0:
            print("\n⚠️  No markets cached")
            print("   This may be okay if markets load on first request")
        
        print("\n✓ Backend is ready for news trading!")
        return True
        
    except Exception as e:
        print(f"❌ Cannot connect to backend: {e}")
        return False

if __name__ == "__main__":
    success = check_backend()
    sys.exit(0 if success else 1)
