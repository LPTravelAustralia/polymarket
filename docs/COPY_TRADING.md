# Copy Trading Guide

## Overview

Copy trading (also called "mirror trading") automatically replicates trades from profitable "smart money" wallets on Polymarket. Instead of developing your own trading strategy, you copy the trades of proven successful traders in real-time.

## How It Works

```
Smart Money Wallet          Your Bot
      ↓                         ↓
   Places Trade    →    Detects Transaction
      ↓                         ↓
   On Blockchain   →    Decodes Trade Details
      ↓                         ↓
   (Market, Side)  →    Replicates Trade
      ↓                         ↓
   Position Opened →    Your Position Opened
```

### Technical Flow

1. **Monitor:** Your bot watches blockchain (Polygon) for transactions from target wallets
2. **Decode:** Extract trade details (market, YES/NO, amount, price)
3. **Replicate:** Execute same trade on your account (scaled to your risk)
4. **Track:** Monitor performance vs original trader

## Finding Smart Money Wallets

### Method 1: Polymarket Leaderboard
- Go to Polymarket homepage → "Top Traders"
- Look for wallets with:
  - High total profit ($10k+)
  - Win rate > 60%
  - Consistent performance over 3+ months
  - Active (trades daily/weekly)

### Method 2: Twitter/Social Media
- Follow Polymarket traders on X (Twitter)
- Example: [@securezer0](https://x.com/securezer0/status/2007570038732271998)
- Many successful traders share their wallet address

### Method 3: Market Top Holders
- Click any Polymarket market
- View "Top Holders" tab
- Copy wallet addresses of largest profitable positions

### Method 4: Manual Analysis
Use PolygonScan to verify wallet profitability:

```bash
# Example wallet to analyze
WALLET=0x1234567890abcdef...

# Check transaction history
curl "https://api.polygonscan.com/api?module=account&action=tokentx&address=$WALLET&apikey=YOUR_KEY" | jq
```

## Example Profitable Wallets

> ⚠️ **Disclaimer:** Past performance doesn't guarantee future results. Always backtest first.

| Wallet | Total Profit | Win Rate | Specialty | Link |
|--------|--------------|----------|-----------|------|
| @gabagool22 | $50k+ | 65% | Politics | [Profile](https://polymarket.com/@gabagool22) |
| (Add more) | - | - | - | - |

## Evaluating Wallet Quality

### Good Traits ✅
- **Consistent profitability** over 3+ months
- **High liquidity markets** (easy to copy at similar prices)
- **Reasonable trade size** (not whale-only trades)
- **Clear strategy** (politics, sports, crypto focus)
- **Active but not overtrading** (1-10 trades/day)

### Red Flags ❌
- **One-time lucky bet** (check history depth)
- **Low liquidity markets** (can't copy at same price)
- **Insider trading suspicion** (too-perfect timing)
- **Whale trader** ($100k+ per trade = hard to copy)
- **Recent losing streak** (momentum changed)

## Implementation with PolygonScan

### Step 1: Get PolygonScan API Key
```bash
# 1. Sign up at https://polygonscan.com
# 2. Go to API section
# 3. Generate free API key
# 4. Add to .env
POLYGONSCAN_API_KEY=ABC123XYZ...
```

### Step 2: Fetch Wallet Transactions
```python
import requests

def get_wallet_trades(wallet_address, api_key):
    """Fetch ERC-1155 token txs (Polymarket shares)"""
    url = "https://api.polygonscan.com/api"
    params = {
        "module": "account",
        "action": "token1155tx",
        "address": wallet_address,
        "startblock": 0,
        "endblock": 99999999,
        "sort": "desc",
        "apikey": api_key
    }
    response = requests.get(url, params=params)
    return response.json()["result"]

# Example
trades = get_wallet_trades("0xABC...", "YOUR_KEY")
print(f"Found {len(trades)} trades")
```

### Step 3: Decode Transaction Details
```python
from web3 import Web3

def decode_trade(tx_hash, api_key):
    """Get full transaction details"""
    url = "https://api.polygonscan.com/api"
    params = {
        "module": "proxy",
        "action": "eth_getTransactionByHash",
        "txhash": tx_hash,
        "apikey": api_key
    }
    response = requests.get(url, params=params)
    tx_data = response.json()["result"]
    
    # Decode input data with Polymarket ABI
    # (See full implementation in src/connectors/copy_trading.py)
    return {
        "market_id": "...",
        "side": "yes",  # or "no"
        "amount": 25.0,
        "price": 0.65
    }
```

### Step 4: Real-Time Monitoring with Alchemy

For instant copying (not 15s delay), use Alchemy WebSocket:

```python
from web3 import Web3
import asyncio

# Connect to Polygon via Alchemy
w3 = Web3(Web3.WebsocketProvider(
    f'wss://polygon-mainnet.g.alchemy.com/v2/{ALCHEMY_KEY}'
))

async def monitor_wallet(wallet_address):
    """Subscribe to pending transactions"""
    filter = w3.eth.filter('pending')
    
    while True:
        for tx_hash in filter.get_new_entries():
            tx = w3.eth.get_transaction(tx_hash)
            if tx['from'].lower() == wallet_address.lower():
                # This is from our target wallet!
                trade_details = decode_polymarket_tx(tx)
                if trade_details:
                    await execute_copy_trade(trade_details)
        await asyncio.sleep(1)
```

## Copy Trading Strategies

### 1. Simple Mirror (1:1)
Copy every trade exactly as they make it.
- **Pros:** Maximum alignment with trader
- **Cons:** Requires same capital size

### 2. Proportional Copying
Copy at 10% of their size.
```python
their_trade_size = 250  # They bet $250
my_trade_size = their_trade_size * 0.10  # I bet $25
```

### 3. Fixed Size Copying
Always copy at your standard size (e.g., $25).
- **Pros:** Consistent risk per trade
- **Cons:** May overweight small trades, underweight large

### 4. Conditional Copying
Only copy if conditions met:
```python
def should_copy(trade, wallet_stats):
    # Only copy if wallet is currently profitable
    if wallet_stats['profit_30d'] < 0:
        return False
    
    # Only copy high-liquidity markets
    if trade['market_liquidity'] < 5000:
        return False
    
    # Only copy if they bet at least $50
    if trade['amount'] < 50:
        return False
    
    return True
```

### 5. Limit Order Copying (Advanced)
Copy trades with price improvement:
```python
def copy_with_offset(original_trade):
    """Try to get better price than trader"""
    if original_trade['side'] == 'yes':
        # For YES bets, try to buy 1% cheaper
        my_price = original_trade['price'] * 0.99
    else:
        # For NO bets, try to buy 1% cheaper
        my_price = original_trade['price'] * 0.99
    
    # Place limit order
    return place_limit_order(
        market=original_trade['market'],
        side=original_trade['side'],
        price=my_price,
        amount=my_trade_size,
        expires_in=300  # 5 minutes
    )
```

## Risk Management

### Position Limits
```python
COPY_MAX_PER_TRADE = 100        # Max $100 per copied trade
COPY_MAX_PER_WALLET = 500       # Max $500 total exposure to one wallet
COPY_MAX_TOTAL = 2000           # Max $2000 across all copied trades
```

### Wallet Health Checks
```python
def check_wallet_health(wallet_address):
    """Stop copying if wallet starts losing"""
    recent_trades = get_last_n_trades(wallet_address, n=10)
    win_rate = calculate_win_rate(recent_trades)
    
    if win_rate < 0.40:  # Less than 40% wins in last 10 trades
        disable_copying(wallet_address)
        send_alert(f"Disabled copying {wallet_address} - win rate dropped to {win_rate:.1%}")
```

### Liquidity Checks
```python
def can_copy_at_similar_price(market_id, original_price, my_size):
    """Check if we can get similar price"""
    orderbook = get_orderbook(market_id)
    
    # Calculate slippage for our order size
    slippage = calculate_slippage(orderbook, my_size)
    
    # Only copy if slippage < 2%
    return slippage < 0.02
```

## Testing & Backtesting

Before enabling copy trading, backtest the wallet:

```python
def backtest_wallet(wallet_address, start_date, end_date):
    """Calculate hypothetical P&L if we copied this wallet"""
    trades = get_wallet_trades_in_range(wallet_address, start_date, end_date)
    
    total_pnl = 0
    for trade in trades:
        # Simulate copying this trade
        entry_price = trade['price']
        exit_price = get_market_resolution_price(trade['market_id'])
        
        if trade['side'] == 'yes':
            pnl = (exit_price - entry_price) * trade['amount']
        else:
            pnl = (entry_price - exit_price) * trade['amount']
        
        total_pnl += pnl
    
    return {
        "total_trades": len(trades),
        "total_pnl": total_pnl,
        "win_rate": calculate_win_rate(trades),
        "avg_profit_per_trade": total_pnl / len(trades)
    }

# Example
results = backtest_wallet("0xABC...", "2024-01-01", "2024-12-31")
print(f"Backtest: {results['total_pnl']:.2f} P&L over {results['total_trades']} trades")
```

## Dashboard Integration

### Copy Trading Panel (Planned UI)
```
┌─────────────────────────────────────┐
│ 📊 Copy Trading Dashboard           │
├─────────────────────────────────────┤
│ Tracked Wallets:                    │
│                                     │
│ ✅ @gabagool22 (0xABC...)          │
│    30d P&L: +$5,234 | Win: 67%     │
│    Copied: 15 trades | My P&L: +$502│
│    [Disable] [Settings]             │
│                                     │
│ ✅ @whale_trader (0xDEF...)        │
│    30d P&L: +$12k | Win: 71%       │
│    Copied: 8 trades | My P&L: +$240 │
│    [Disable] [Settings]             │
│                                     │
│ [+ Add Wallet]                      │
├─────────────────────────────────────┤
│ Recent Copy Activity:               │
│ [07:15] Copied @gabagool22          │
│         YES $25 on "Bitcoin $150k"  │
│         @ 0.27 (orig: 0.27)         │
│                                     │
│ [07:02] Copied @whale_trader        │
│         NO $50 on "ETH $8k by Feb"  │
│         @ 0.42 (orig: 0.41) ⚠️+1%   │
└─────────────────────────────────────┘
```

## Legal & Ethical Considerations

### ✅ Allowed
- Monitoring public blockchain data
- Replicating trades on your own account
- Using PolygonScan and Alchemy APIs
- Backtesting historical wallet performance

### ⚠️ Gray Area
- Mempool front-running (getting ahead of their trade)
- Copying very large traders (may impact market)

### ❌ Not Allowed
- Insider trading (copying wallets with non-public info)
- Market manipulation
- Sharing copied trades publicly in real-time (may violate Polymarket ToS)

**Recommendation:** Use copy trading for personal use only. Add 1-5 second delay to avoid front-running accusations.

## Cost Analysis

### API Costs (Free Tier Sufficient for Start)
| Service | Free Tier | Cost After |
|---------|-----------|------------|
| PolygonScan | 5 calls/sec | $199/mo for 15 calls/sec |
| Alchemy | 300M compute units/mo | $49/mo for more |
| Polymarket | Unlimited | Free |

### Example Monthly Cost
```
Monitoring 5 wallets:
- PolygonScan: $0 (under 5 calls/sec)
- Alchemy: $0 (under 300M units)
- Total: $0 for small-scale copy trading
```

### Scaling to 50+ Wallets
- Need premium PolygonScan: $199/mo
- Need paid Alchemy: $49/mo
- Total: $248/mo

## Getting Started Checklist

- [ ] Get PolygonScan API key
- [ ] Get Alchemy or Infura API key
- [ ] Find 1-3 profitable wallets to track
- [ ] Backtest wallets over past 6 months
- [ ] Implement transaction monitoring
- [ ] Add copy execution logic
- [ ] Set risk limits (max per trade, per wallet)
- [ ] Build dashboard UI
- [ ] Test with paper trading first
- [ ] Enable live copying with small amounts
- [ ] Monitor performance daily

## Next Steps

1. **Read:** [PolyCop Documentation](https://polycop.gitbook.io/polycop-docs) for inspiration
2. **Analyze:** Pick a wallet and run historical analysis
3. **Build:** Implement PolygonScan integration in `src/connectors/copy_trading.py`
4. **Test:** Backtest thoroughly before going live
5. **Scale:** Add more wallets as you prove profitability

## References

- [PolyCop Docs](https://polycop.gitbook.io/polycop-docs) - Similar Telegram bot
- [PolygonScan API](https://docs.polygonscan.com) - Blockchain data
- [Alchemy Docs](https://docs.alchemy.com) - Real-time blockchain access
- [Polymarket API](https://docs.polymarket.com) - Market data
- Example wallet: [@gabagool22](https://polymarket.com/@gabagool22)

---

*Questions? Open an issue on GitHub or check the main ROADMAP.md*
