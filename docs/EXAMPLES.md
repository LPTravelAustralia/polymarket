# Examples and Use Cases

This document provides practical examples of using the Polymarket Trading Bot.

## Table of Contents

1. [Basic Market Monitoring](#basic-market-monitoring)
2. [Simple Trading Bot](#simple-trading-bot)
3. [Custom Strategy](#custom-strategy)
4. [AI-Powered Trading](#ai-powered-trading)
5. [Fee Collection Setup](#fee-collection-setup)
6. [Risk Management](#risk-management)
7. [Multi-Market Trading](#multi-market-trading)

## Basic Market Monitoring

### Example: Find High-Liquidity Markets

```python
from src.core.config import load_config
from src.core.client import PolymarketClient
from src.core.market_monitor import MarketMonitor

# Setup
config = load_config()
client = PolymarketClient(config)
monitor = MarketMonitor(client, config)

# Find markets with at least $10k liquidity
markets = monitor.discover_markets(min_liquidity=10000)

print(f"Found {len(markets)} high-liquidity markets:\n")

for i, market in enumerate(markets[:10], 1):
    question = market.get('question', 'Unknown')
    liquidity = market.get('liquidity', 0)
    volume = market.get('volume', 0)
    
    print(f"{i}. {question}")
    print(f"   Liquidity: ${liquidity:,.2f}")
    print(f"   24h Volume: ${volume:,.2f}\n")
```

### Example: Check Specific Market

```python
# Get specific market by condition ID
condition_id = "0x1234567890abcdef..."
market = client.get_market(condition_id)

if market:
    print(f"Question: {market['question']}")
    print(f"End Date: {market.get('end_date')}")
    
    # Get current prices
    prices = monitor.get_market_prices(condition_id)
    
    for token_id, price in prices.items():
        print(f"Token {token_id}: {price:.3f}")
```

## Simple Trading Bot

### Example: Basic Momentum Strategy

```python
from src.agents.momentum_agent import MomentumAgent
from src.core.config import load_config

# Configure for safe testing
config = load_config()
config.dry_run = True  # No real trades
config.default_trade_size = 10  # Small size

# Create and run agent
agent = MomentumAgent(config)

# Discover and analyze markets
markets = agent.monitor.discover_markets()

for market in markets[:5]:
    # Analyze market
    analysis = agent.analyze_market(market)
    
    print(f"\nMarket: {market['question']}")
    
    for token in analysis['tokens']:
        print(f"  {token['outcome']}: momentum score = {token['momentum_score']:.2f}")
    
    # Generate signal
    signal = agent.generate_trading_signal(analysis)
    
    if signal:
        print(f"  ✅ Signal: {signal['side']} {signal['size']} @ {signal['price']:.3f}")
        print(f"     Reason: {signal['reason']}")
```

### Example: Automated Trading Loop

```python
import time
from src.agents.momentum_agent import MomentumAgent
from src.core.config import load_config

config = load_config()
config.auto_trade = True  # Enable auto-trading
config.monitoring_interval = 300  # Check every 5 minutes

agent = MomentumAgent(config)

print("Starting automated trading bot...")

try:
    while True:
        print(f"\n{'='*60}")
        print(f"Trading Cycle - {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print('='*60)
        
        # Run trading cycle
        agent.run()
        
        # Show performance
        stats = agent.get_performance_stats()
        print(f"\nPerformance:")
        print(f"  Total Trades: {stats['total_trades']}")
        print(f"  Win Rate: {stats['win_rate']:.1%}")
        print(f"  P&L: ${stats['total_profit_loss']:.2f}")
        print(f"  Fees Collected: ${stats['total_fees_collected']:.2f}")
        
        # Wait for next cycle
        print(f"\nWaiting {config.monitoring_interval} seconds...")
        time.sleep(config.monitoring_interval)

except KeyboardInterrupt:
    print("\n\nBot stopped by user")
    print(f"Final Stats: {agent.get_performance_stats()}")
```

## Custom Strategy

### Example: Create Volume-Based Strategy

```python
from src.agents.base_agent import BaseAgent
from typing import Dict, Any, Optional

class VolumeAgent(BaseAgent):
    """Trade based on volume spikes"""
    
    def analyze_market(self, market: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze market volume"""
        condition_id = market.get('condition_id')
        volume_24h = market.get('volume', 0)
        liquidity = market.get('liquidity', 0)
        
        # Calculate volume/liquidity ratio
        volume_ratio = volume_24h / liquidity if liquidity > 0 else 0
        
        analysis = {
            'condition_id': condition_id,
            'question': market.get('question'),
            'volume_24h': volume_24h,
            'liquidity': liquidity,
            'volume_ratio': volume_ratio,
            'high_activity': volume_ratio > 2.0  # 2x volume vs liquidity
        }
        
        return analysis
    
    def generate_trading_signal(self, analysis: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Generate signal on high volume"""
        if not analysis['high_activity']:
            return None
        
        # High volume = market moving, buy the trending outcome
        condition_id = analysis['condition_id']
        prices = self.monitor.get_market_prices(condition_id)
        
        # Buy the most expensive token (trending outcome)
        if prices:
            best_token = max(prices.items(), key=lambda x: x[1])
            token_id, price = best_token
            
            return {
                'token_id': token_id,
                'side': 'BUY',
                'price': price,
                'size': self.config.default_trade_size,
                'reason': f'High volume spike (ratio: {analysis["volume_ratio"]:.2f})'
            }
        
        return None

# Use the custom agent
config = load_config()
agent = VolumeAgent(config)
agent.run()
```

## AI-Powered Trading

### Example: Using AI Agent

```python
from src.agents.ai_agent import AIAgent
from src.core.config import load_config

# Configure with AI
config = load_config()
config.use_ai_predictions = True
config.openai_api_key = "sk-..."  # Your OpenAI key
config.dry_run = True

# Create AI agent
agent = AIAgent(config)

# Analyze a specific market
markets = agent.monitor.discover_markets()
market = markets[0]

print(f"Analyzing: {market['question']}\n")

analysis = agent.analyze_market(market)

# Show AI prediction
if 'ai_prediction' in analysis:
    pred = analysis['ai_prediction']
    
    print("AI Prediction:")
    print(f"  Confidence: {pred.get('confidence', 0):.1%}")
    print(f"  Reasoning: {pred.get('reasoning', 'N/A')}")
    
    for p in pred.get('predictions', []):
        print(f"\n  Outcome: {p['outcome']}")
        print(f"    Probability: {p['probability']:.1%}")
        print(f"    Recommend: {'✅ BUY' if p['recommend_buy'] else '❌ PASS'}")

# Generate trading signal
signal = agent.generate_trading_signal(analysis)

if signal:
    print(f"\n📊 Trading Signal Generated!")
    print(f"  Action: {signal['side']}")
    print(f"  Size: {signal['size']} USDC")
    print(f"  Price: {signal['price']:.3f}")
    print(f"  AI Edge: {signal.get('ai_probability', 0) - signal['price']:.3f}")
```

### Example: Batch AI Analysis

```python
from src.agents.ai_agent import AIAgent
from src.core.config import load_config
import time

config = load_config()
config.use_ai_predictions = True

agent = AIAgent(config)

# Get top markets
markets = agent.monitor.discover_markets(min_liquidity=5000)

print(f"Analyzing {len(markets)} markets with AI...\n")

opportunities = []

for i, market in enumerate(markets[:20], 1):  # Limit to avoid API costs
    print(f"[{i}/20] {market['question'][:60]}...")
    
    analysis = agent.analyze_market(market)
    signal = agent.generate_trading_signal(analysis)
    
    if signal:
        opportunities.append({
            'market': market,
            'signal': signal,
            'analysis': analysis
        })
        print(f"  ✅ Opportunity found!")
    
    time.sleep(1)  # Rate limiting

print(f"\n\n{'='*60}")
print(f"Found {len(opportunities)} trading opportunities")
print('='*60)

for i, opp in enumerate(opportunities, 1):
    print(f"\n{i}. {opp['market']['question']}")
    print(f"   Signal: {opp['signal']['side']} @ {opp['signal']['price']:.3f}")
    print(f"   Reason: {opp['signal']['reason']}")
```

## Fee Collection Setup

### Example: Configure for Fee Collection

```python
from src.core.config import Config
from src.core.fee_collector import FeeCollector

# Setup with fees
config = Config(
    fee_percentage=0.015,  # 1.5%
    fee_wallet_address="0xYourFeeWallet..."
)

collector = FeeCollector(config)

# Simulate some trades
trades = [
    {'profit': 100, 'user': '0xuser1...'},
    {'profit': 250, 'user': '0xuser2...'},
    {'profit': -50, 'user': '0xuser3...'},  # Loss = no fee
    {'profit': 75, 'user': '0xuser1...'},
]

for trade in trades:
    profit = trade['profit']
    user = trade['user']
    
    if profit > 0:
        fee = collector.calculate_fee(profit)
        record = collector.collect_fee(
            from_address=user,
            amount=fee,
            transaction_hash=f"0xtx_{user}"
        )
        print(f"Collected ${fee:.2f} from {user[:12]}... (profit: ${profit:.2f})")
    else:
        print(f"No fee from {user[:12]}... (loss: ${profit:.2f})")

# Show summary
print(f"\nTotal fees collected: ${collector.get_total_fees():.2f}")
```

## Risk Management

### Example: Conservative Risk Settings

```python
from src.core.config import Config
from src.agents.momentum_agent import MomentumAgent

# Conservative configuration
config = Config(
    default_trade_size=10,        # Small trades
    max_position_size=100,        # Low max position
    risk_percentage=0.01,         # Only 1% risk per trade
    min_liquidity=10000,          # High liquidity only
    dry_run=False,
    auto_trade=True
)

agent = MomentumAgent(config)

# The agent will automatically respect these limits
agent.run()
```

### Example: Check Risk Before Trading

```python
def safe_trade(agent, token_id, side, size, price):
    """Execute trade with extra risk checks"""
    
    # Check 1: Position size
    trade_value = size * price
    if trade_value > agent.config.max_position_size:
        print(f"❌ Trade too large: ${trade_value:.2f}")
        return None
    
    # Check 2: Market depth
    depth = agent.monitor.analyze_market_depth(token_id)
    if depth['spread_percentage'] > 5.0:
        print(f"❌ Spread too wide: {depth['spread_percentage']:.2f}%")
        return None
    
    # Check 3: Liquidity
    if depth['total_bid_volume'] < 100:
        print(f"❌ Insufficient liquidity: {depth['total_bid_volume']:.2f}")
        return None
    
    # All checks passed
    print("✅ Risk checks passed, executing trade...")
    return agent.execute_trade(token_id, side, size, price)
```

## Multi-Market Trading

### Example: Trade Multiple Markets Simultaneously

```python
from src.agents.momentum_agent import MomentumAgent
from src.core.config import load_config

config = load_config()
config.max_concurrent_trades = 5

agent = MomentumAgent(config)

# Get markets in different categories
markets = agent.monitor.discover_markets()

# Group by category/tag
by_category = {}
for market in markets:
    tags = market.get('tags', ['other'])
    category = tags[0] if tags else 'other'
    
    if category not in by_category:
        by_category[category] = []
    by_category[category].append(market)

print(f"Found {len(by_category)} categories")

# Trade top market in each category
active_trades = []

for category, cat_markets in by_category.items():
    if len(active_trades) >= config.max_concurrent_trades:
        break
    
    # Analyze best market in category
    best_market = max(cat_markets, key=lambda x: x.get('liquidity', 0))
    
    analysis = agent.analyze_market(best_market)
    signal = agent.generate_trading_signal(analysis)
    
    if signal:
        print(f"\n📊 {category}: {best_market['question'][:50]}...")
        result = agent.execute_trade(
            signal['token_id'],
            signal['side'],
            signal['size'],
            signal['price']
        )
        
        if result:
            active_trades.append(result)
            print(f"  ✅ Trade executed")

print(f"\n{len(active_trades)} trades active across {len(by_category)} categories")
```

## Advanced Examples

### Example: Combine Multiple Strategies

```python
from src.agents.momentum_agent import MomentumAgent
from src.agents.arbitrage_agent import ArbitrageAgent
from src.core.config import load_config

config = load_config()

momentum = MomentumAgent(config)
arbitrage = ArbitrageAgent(config)

markets = momentum.monitor.discover_markets()

for market in markets:
    # Try arbitrage first (safer)
    arb_analysis = arbitrage.analyze_market(market)
    if arb_analysis['has_arbitrage']:
        print(f"🎯 Arbitrage: {market['question']}")
        arbitrage.execute_arbitrage(arb_analysis)
        continue
    
    # Fall back to momentum
    mom_analysis = momentum.analyze_market(market)
    signal = momentum.generate_trading_signal(mom_analysis)
    
    if signal:
        print(f"📈 Momentum: {market['question']}")
        momentum.execute_trade(
            signal['token_id'],
            signal['side'],
            signal['size'],
            signal['price']
        )
```

### Example: Backtesting (Simulated)

```python
from src.agents.momentum_agent import MomentumAgent
from src.core.config import load_config
import time

config = load_config()
config.dry_run = True  # Backtest mode

agent = MomentumAgent(config)

# Simulate 100 trading cycles
results = []

for cycle in range(100):
    print(f"Cycle {cycle + 1}/100")
    
    agent.run()
    stats = agent.get_performance_stats()
    
    results.append({
        'cycle': cycle,
        'trades': stats['total_trades'],
        'win_rate': stats['win_rate'],
        'pnl': stats['total_profit_loss']
    })
    
    time.sleep(60)  # Wait 1 minute between cycles

# Analyze results
import statistics

all_pnl = [r['pnl'] for r in results]
print(f"\nBacktest Results:")
print(f"  Total P&L: ${sum(all_pnl):.2f}")
print(f"  Average P&L: ${statistics.mean(all_pnl):.2f}")
print(f"  Std Dev: ${statistics.stdev(all_pnl):.2f}")
print(f"  Best: ${max(all_pnl):.2f}")
print(f"  Worst: ${min(all_pnl):.2f}")
```

## Conclusion

These examples demonstrate the flexibility and power of the Polymarket Trading Bot. You can:

- Monitor markets in real-time
- Implement custom strategies
- Use AI for predictions
- Manage risk effectively
- Collect fees from users
- Trade multiple markets
- Combine strategies

For more information:
- [Quick Start Guide](QUICKSTART.md)
- [API Documentation](API.md)
- [Architecture](ARCHITECTURE.md)
