#!/usr/bin/env python3
"""
Real-time Frontend Dashboard
Simulates frontend monitoring the backend while news monitor runs on SSH server
Shows live updates from backend API
"""
import requests
import json
import time
import threading
from datetime import datetime
from collections import deque

BASE_URL = "http://localhost:8000"

class RealtimeDashboard:
    """Frontend dashboard showing real-time backend state"""
    
    def __init__(self):
        self.status_history = deque(maxlen=20)
        self.trade_history = deque(maxlen=10)
        self.running = False
    
    def fetch_status(self):
        """Fetch current bot status from backend"""
        try:
            response = requests.get(f"{BASE_URL}/api/status", timeout=2)
            if response.status_code == 200:
                return response.json()
        except:
            pass
        return None
    
    def fetch_stats(self):
        """Fetch trading statistics from backend"""
        try:
            response = requests.get(f"{BASE_URL}/api/stats/summary", timeout=2)
            if response.status_code == 200:
                return response.json()
        except:
            pass
        return None
    
    def fetch_activity(self):
        """Fetch recent activity/trades from backend"""
        try:
            response = requests.get(f"{BASE_URL}/api/activity?limit=5", timeout=2)
            if response.status_code == 200:
                return response.json()
        except:
            pass
        return None
    
    def display_header(self):
        """Display dashboard header"""
        print("\n" + "=" * 90)
        print("  POLYMARKET TRADING BOT - REAL-TIME FRONTEND DASHBOARD")
        print("  Monitoring Backend at:", BASE_URL)
        print("=" * 90)
    
    def display_status(self, status):
        """Display bot status section"""
        if not status:
            print("  ❌ Cannot connect to backend")
            return
        
        print("\n📊 BOT STATUS")
        print("─" * 90)
        running = "🟢 RUNNING" if status.get('running') else "🔴 STOPPED"
        print(f"  Status: {running}")
        print(f"  Trades Today: {status.get('trades_today', 0)}")
        print(f"  Total PnL: ${status.get('total_pnl', 0):.2f}")
        print(f"  Win Rate: {status.get('win_rate', 0):.1%}")
        print(f"  Active Positions: {status.get('active_positions', 0)}")
        print(f"  Last Update: {status.get('last_update', 'never')}")
    
    def display_stats(self, stats):
        """Display trading statistics"""
        if not stats:
            return
        
        print("\n📈 TRADING STATISTICS")
        print("─" * 90)
        if 'today' in stats:
            print(f"  Today:")
            print(f"    • Trades: {stats['today'].get('trades', 0)}")
            print(f"    • PnL: ${stats['today'].get('pnl', 0):.2f}")
            print(f"    • Win Rate: {stats['today'].get('win_rate', 0):.1%}")
        
        if 'positions' in stats:
            print(f"  Positions:")
            print(f"    • Active: {stats['positions'].get('active', 0)}")
            print(f"    • Pending: {stats['positions'].get('pending', 0)}")
        
        if 'bot' in stats:
            print(f"  Bot:")
            print(f"    • Status: {stats['bot'].get('status', 'unknown')}")
            print(f"    • Exposure: ${float(stats['bot'].get('exposure', 0)):.2f}")
    
    def display_activity(self, activity):
        """Display recent trades/activity"""
        if not activity:
            return
        
        print("\n📋 RECENT ACTIVITY")
        print("─" * 90)
        if isinstance(activity, list) and len(activity) > 0:
            for i, item in enumerate(activity[:3], 1):
                print(f"  {i}. {str(item)[:85]}...")
        else:
            print("  No recent activity")
    
    def display_footer(self):
        """Display footer with instructions"""
        print("\n" + "─" * 90)
        print("  💡 While this dashboard refreshes every 5 seconds,")
        print("  on your SSH server, run: python3 scripts/run_news_monitor.py --once --dry-run")
        print("  to start finding signals and executing paper trades!")
        print("\n  The frontend will show:")
        print("    ✅ New trades as they execute")
        print("    ✅ PnL updates in real-time")
        print("    ✅ Signal details and reasoning")
        print("    ✅ Market impact analysis")
        print("=" * 90 + "\n")
    
    def run(self, duration=60):
        """Run dashboard for specified duration (seconds)"""
        self.display_header()
        self.display_footer()
        
        print(f"⏱️  Refreshing every 5 seconds for {duration} seconds...")
        print("(Press Ctrl+C to stop)\n")
        
        start_time = time.time()
        refresh_count = 0
        
        try:
            while (time.time() - start_time) < duration:
                refresh_count += 1
                timestamp = datetime.now().strftime("%H:%M:%S")
                
                # Fetch data from backend
                status = self.fetch_status()
                stats = self.fetch_stats()
                activity = self.fetch_activity()
                
                # Clear screen (works on Unix/Linux)
                import os
                os.system('clear' if os.name == 'posix' else 'cls')
                
                # Display header with timestamp
                print(f"\n[{timestamp}] Real-time Backend Monitor - Refresh #{refresh_count}")
                print("=" * 90)
                
                # Display sections
                self.display_status(status)
                self.display_stats(stats)
                self.display_activity(activity)
                
                self.display_footer()
                
                print(f"Next refresh in 5 seconds... (Ctrl+C to stop)")
                time.sleep(5)
        
        except KeyboardInterrupt:
            print("\n\n✋ Dashboard stopped by user")
            print("=" * 90)
            print("\n📊 FINAL SUMMARY:")
            print(f"  • Refreshes: {refresh_count}")
            print(f"  • Duration: {time.time() - start_time:.1f}s")
            print(f"  • Backend connection: {'✅ OK' if status else '❌ FAILED'}")
            print("\nTo run paper trading:")
            print("  SSH to your server and run:")
            print("  python3 scripts/run_news_monitor.py --once --dry-run\n")


def main():
    """Main entry point"""
    print("\n🚀 Starting Real-Time Frontend Dashboard...")
    print("   Connecting to backend at", BASE_URL)
    
    # Test connection first
    try:
        response = requests.get(f"{BASE_URL}/", timeout=2)
        if response.status_code == 200:
            print("   ✅ Backend connection OK\n")
        else:
            print("   ⚠️  Backend responded but with unexpected status\n")
    except Exception as e:
        print(f"   ❌ Cannot connect to backend: {e}")
        print("   Make sure it's running: python3 backend/main.py\n")
        return
    
    # Run dashboard for 120 seconds (2 minutes)
    dashboard = RealtimeDashboard()
    dashboard.run(duration=120)


if __name__ == "__main__":
    main()
