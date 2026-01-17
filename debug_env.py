#!/usr/bin/env python3
"""Debug script to check environment variable loading"""
import os
import sys
from pathlib import Path

print("=" * 80)
print("ENVIRONMENT VARIABLE DEBUGGING")
print("=" * 80)

# Step 1: Check .env file
env_path = Path.home() / "polymarket" / ".env"
print(f"\n1. Checking .env file location:")
print(f"   Expected path: {env_path}")
print(f"   Exists: {env_path.exists()}")

if env_path.exists():
    print(f"   Readable: {os.access(env_path, os.R_OK)}")
    print(f"   Size: {env_path.stat().st_size} bytes")
    
    # Show first 5 lines without printing actual secrets
    print(f"   First 5 lines (keys only):")
    with open(env_path) as f:
        for i, line in enumerate(f):
            if i >= 5:
                break
            if "=" in line:
                key = line.split("=")[0]
                print(f"      {key}")

# Step 2: Check os.environ before dotenv
print(f"\n2. NEWSAPI_KEY in os.environ (BEFORE dotenv): {('NEWSAPI_KEY' in os.environ)}")
if 'NEWSAPI_KEY' in os.environ:
    print(f"   Value length: {len(os.environ['NEWSAPI_KEY'])}")

# Step 3: Manually load dotenv
from dotenv import load_dotenv
result = load_dotenv(env_path)
print(f"\n3. Manual load_dotenv result: {result}")
print(f"   NEWSAPI_KEY in os.environ (AFTER dotenv): {('NEWSAPI_KEY' in os.environ)}")
if 'NEWSAPI_KEY' in os.environ:
    print(f"   Value length: {len(os.environ['NEWSAPI_KEY'])}")
    print(f"   First 20 chars: {os.environ['NEWSAPI_KEY'][:20]}")

# Step 4: Try loading via Pydantic
print(f"\n4. Loading via Pydantic config:")
try:
    sys.path.insert(0, '/home/hello/polymarket')
    from src.core.config import Settings
    settings = Settings()
    print(f"   newsapi_key loaded: {bool(settings.newsapi_key)}")
    if settings.newsapi_key:
        print(f"   Value length: {len(settings.newsapi_key)}")
        print(f"   First 20 chars: {settings.newsapi_key[:20]}")
    else:
        print(f"   newsapi_key is: {repr(settings.newsapi_key)}")
except Exception as e:
    print(f"   ERROR: {e}")
    import traceback
    traceback.print_exc()

# Step 5: Check config.py's env_file path
print(f"\n5. Checking config.py env_file path:")
try:
    import inspect
    from src.core.config import Settings
    source = inspect.getsource(Settings.model_config)
    # Find env_file setting
    for line in source.split('\n'):
        if 'env_file' in line:
            print(f"   {line.strip()}")
except:
    pass

print("\n" + "=" * 80)
