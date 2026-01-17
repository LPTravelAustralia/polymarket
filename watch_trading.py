#!/usr/bin/env python3
"""
Real Trading Monitor
Watch the backend for actual trades, PnL changes, and activity
"""
import requests
import json
import time
from datetime import datetime

import os

BASE_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

class TradingMonitor:
    def __init__(self):
        self.last_stats = None
        self.last_trades = 0
        self.last_pnl = 0.0
        self.last_positions = 0
    
    def get_current_stats(self):
        """Get current trading statistics"""
        try:
            response = requests.get(f"{BASE_URL}/api/stats/summary", timeout=3)
            return response.json() if response.status_code == 200 else None
        except:
            return None
    
    def get_status(self):
        """Get bot status"""
        try:
            response = requests.get(f"{BASE_URL}/api/status", timeout=3)
            return response.json() if response.status_code == 200 else None
        except:
            return None
    
    def get_activity(self):
        """Get recent activity"""
        try:
            response = requests.get(f"{BASE_URL}/api/activity?limit=10", timeout=3)
            return response.json() if response.status_code == 200 else None
        except:
            return None
    
    def watch(self, duration=120):
        """Watch system for specified duration"""
        print("\n" + "="*80)
        print("  TRADING MONITOR - WATCHING FOR ACTUAL TRADES & PnL")
        print("="*80)
        
        start_time = time.time()
        check_num = 0
        
        try:
            while (time.time() - start_time) < duration:
                check_num += 1
                now = datetime.now().strftime("%H:%M:%S")
                
                # Get current data
                status = self.get_status()
                stats = self.get_current_stats()
                activity = self.get_activity()
                
                print(f"\n[{now}] CHECK #{check_num}")
                print("-" * 80)
                
                if not status:
                    print("  ❌ Cannot reach backend!")
                    time.sleep(3)
                    continue
                
                # Check for changes
                trades_today = status.get('trades_today', 0)
                total_pnl = status.get('total_pnl', 0)
                positions = status.get('active_positions', 0)
                
                # Detect changes
                trade_change = trades_today - self.last_trades
                pnl_change = total_pnl - self.last_pnl
                position_change = positions - self.last_positions
                
                # Display status
                print(f"  🤖 Bot Status: {'🟢 RUNNING' if status.get('running') else '🔴 STOPPED'}")
                print(f"  📊 Trades Today: {trades_today}", end="")
                if trade_change != 0:
                    print(f" ↑ ({trade_change:+d})")
                else:
                    print()
                
                print(f"  💰 Total PnL: ${total_pnl:.2f}", end="")
                if pnl_change != 0:
                    emoji = "📈" if pnl_change > 0 else "📉"
                    print(f" {emoji} ({pnl_change:+.2f})")
                else:
                    print()
                
                print(f"  📈 Active Positions: {positions}", end="")
                if position_change != 0:
                    print(f" ({position_change:+d})")
                else:
                    print()
                
                # Show recent activity if any
                if activity and isinstance(activity, list) and len(activity) > 0:
                    print(f"\n  📋 RECENT ACTIVITY ({len(activity)} items):")
                    for i, item in enumerate(activity[:3], 1):
                        activity_str = json.dumps(item) if isinstance(item, dict) else str(item)
                        print(f"     {i}. {activity_str[:75]}...")
                
                # Show detailed stats if available
                if stats:
                    if 'today' in stats:
                        print(f"\n  📊 TODAY'S SUMMARY:")
                        print(f"     • Trades: {stats['today'].get('trades', 0)}")
                        print(f"     • PnL: ${stats['today'].get('pnl', 0):.2f}")
                        print(f"     • Win Rate: {stats['today'].get('win_rate', 0):.1%}")
                
                # Update tracking
                self.last_trades = trades_today
                self.last_pnl = total_pnl
                self.last_positions = positions
                self.last_stats = stats
                
                # Wait before next check
                elapsed = time.time() - start_time
                remaining = duration - elapsed
                if remaining > 0:
                    print(f"\n  ⏱️  Next check in 5 seconds... ({remaining:.0f}s remaining)")
                
                time.sleep(5)
        
        except KeyboardInterrupt:
            print("\n\n✋ MONITOR STOPPED")
        
        # Final summary
        print("\n" + "="*80)
        print("  FINAL TRADING SUMMARY")
        print("="*80)
        status = self.get_status()
        if status:
            print(f"  Total Trades: {status.get('trades_today', 0)}")
            print(f"  Final PnL: ${status.get('total_pnl', 0):.2f}")
            print(f"  Final Positions: {status.get('active_positions', 0)}")
            print(f"  Win Rate: {status.get('win_rate', 0):.1%}")
        print("="*80 + "\n")


if __name__ == "__main__":
    print("\n🚀 Starting Trading Monitor...")
    print("   This will watch the backend for actual trades and PnL changes")
    
    # Test connection
    try:
        r = requests.get(f"{BASE_URL}/api/status", timeout=2)
        if r.status_code == 200:
            print("   ✅ Connected to backend\n")
        else:
            print("   ⚠️  Backend not responding\n")
    except Exception as e:
        print(f"   ❌ Cannot connect: {e}")
        print("   Start backend with: python3 backend/main.py\n")
        exit(1)
    
    monitor = TradingMonitor()
    monitor.watch(duration=120)  # Watch for 2 minutes
