#!/usr/bin/env python3
"""
Web Dashboard for Polymarket Trading Bot
A simple Flask web interface to view markets and control the bot.
"""
import os
import sys
from pathlib import Path
from datetime import datetime
from threading import Thread
import time

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from flask import Flask, render_template, jsonify, request
from src.core.gamma_client import GammaMarketClient
from src.core.config import load_config

app = Flask(__name__, template_folder='templates', static_folder='static')

# Global state
bot_state = {
    "running": False,
    "last_update": None,
    "trades_today": 0,
    "total_pnl": 0.0,
    "messages": []
}

# Initialize clients
gamma_client = GammaMarketClient()


def add_message(msg: str):
    """Add a message to the bot log"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    bot_state["messages"].insert(0, f"[{timestamp}] {msg}")
    bot_state["messages"] = bot_state["messages"][:50]  # Keep last 50


@app.route('/')
def index():
    """Main dashboard page"""
    return render_template('index.html')


@app.route('/api/markets')
def get_markets():
    """Get current markets from Polymarket"""
    try:
        limit = request.args.get('limit', 10, type=int)
        markets = gamma_client.get_current_markets(limit=limit)
        
        # Format for frontend
        formatted = []
        for m in markets:
            formatted.append({
                "id": m.get("condition_id", ""),
                "question": m.get("question", "Unknown"),
                "liquidity": float(m.get("liquidity", 0)),
                "volume": float(m.get("volume", 0)),
                "outcomes": m.get("outcomes", ["Yes", "No"]),
                "outcome_prices": m.get("outcomePrices", "[0.5, 0.5]"),
                "end_date": m.get("end_date_iso", ""),
                "active": m.get("active", False),
                "closed": m.get("closed", False)
            })
        
        return jsonify({"success": True, "markets": formatted})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/search')
def search_markets():
    """Search markets by keyword"""
    try:
        query = request.args.get('q', '')
        if not query:
            return jsonify({"success": False, "error": "No query provided"})
        
        markets = gamma_client.search_markets(query, limit=20)
        
        formatted = []
        for m in markets:
            formatted.append({
                "id": m.get("condition_id", ""),
                "question": m.get("question", "Unknown"),
                "liquidity": float(m.get("liquidity", 0)),
                "volume": float(m.get("volume", 0)),
                "outcomes": m.get("outcomes", ["Yes", "No"]),
                "outcome_prices": m.get("outcomePrices", "[0.5, 0.5]"),
            })
        
        return jsonify({"success": True, "markets": formatted, "query": query})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/status')
def get_status():
    """Get bot status"""
    return jsonify({
        "running": bot_state["running"],
        "last_update": bot_state["last_update"],
        "trades_today": bot_state["trades_today"],
        "total_pnl": bot_state["total_pnl"],
        "messages": bot_state["messages"][:20]
    })


@app.route('/api/bot/start', methods=['POST'])
def start_bot():
    """Start the trading bot"""
    if bot_state["running"]:
        return jsonify({"success": False, "error": "Bot already running"})
    
    bot_state["running"] = True
    add_message("🚀 Bot started")
    
    # In production, you'd start a background thread here
    # For demo, we just set the state
    
    return jsonify({"success": True, "message": "Bot started"})


@app.route('/api/bot/stop', methods=['POST'])
def stop_bot():
    """Stop the trading bot"""
    if not bot_state["running"]:
        return jsonify({"success": False, "error": "Bot not running"})
    
    bot_state["running"] = False
    add_message("🛑 Bot stopped")
    
    return jsonify({"success": True, "message": "Bot stopped"})


@app.route('/api/bot/analyze', methods=['POST'])
def analyze_market():
    """Analyze a specific market (demo)"""
    data = request.json or {}
    market_id = data.get('market_id', '')
    question = data.get('question', 'Unknown market')
    
    add_message(f"🔍 Analyzing: {question[:50]}...")
    
    # In production, this would call the SuperforecasterAgent
    # For demo, return mock analysis
    return jsonify({
        "success": True,
        "analysis": {
            "market": question,
            "recommendation": "HOLD",
            "confidence": 0.65,
            "reasoning": "Market shows balanced probabilities. Wait for clearer signal.",
            "predicted_probability": 0.52
        }
    })


if __name__ == '__main__':
    print("=" * 60)
    print("🤖 Polymarket Trading Bot - Web Dashboard")
    print("=" * 60)
    print("\n📊 Open your browser to: http://localhost:5000\n")
    app.run(host='0.0.0.0', port=5000, debug=True)
