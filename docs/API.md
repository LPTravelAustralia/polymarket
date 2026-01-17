# API Documentation

## PolymarketClient

### Overview
The `PolymarketClient` class provides a high-level interface to interact with the Polymarket API.

### Initialization

```python
from src.core.client import PolymarketClient
from src.core.config import load_config

config = load_config()
client = PolymarketClient(config)
```

### Methods

#### get_markets(limit: int = 100, offset: int = 0) → List[Dict]

Fetch list of active markets.

**Parameters:**
- `limit`: Maximum number of markets to return (default: 100)
- `offset`: Pagination offset (default: 0)

**Returns:** List of market dictionaries

**Example:**
```python
markets = client.get_markets(limit=50)
for market in markets:
    print(f"{market['question']}: {market['liquidity']}")
```

#### get_market(condition_id: str) → Optional[Dict]

Get specific market by condition ID.

**Parameters:**
- `condition_id`: Unique market identifier

**Returns:** Market data dictionary or None

**Example:**
```python
market = client.get_market("0x1234...")
if market:
    print(market['question'])
```

#### get_orderbook(token_id: str) → Dict

Get orderbook for a specific token.

**Parameters:**
- `token_id`: Token identifier

**Returns:** Dictionary with 'bids' and 'asks' arrays

**Example:**
```python
orderbook = client.get_orderbook("0x5678...")
best_bid = orderbook['bids'][0]['price']
best_ask = orderbook['asks'][0]['price']
```

#### place_order(token_id: str, side: str, price: float, size: float, order_type: str = "GTC") → Optional[Dict]

Place a trading order.

**Parameters:**
- `token_id`: Token to trade
- `side`: "BUY" or "SELL"
- `price`: Price per share (0.0 to 1.0)
- `size`: Number of shares
- `order_type`: Order type (default: "GTC" - Good Till Cancelled)

**Returns:** Order response or None

**Example:**
```python
result = client.place_order(
    token_id="0x5678...",
    side="BUY",
    price=0.65,
    size=10
)
```

#### cancel_order(order_id: str) → bool

Cancel an existing order.

**Parameters:**
- `order_id`: Order identifier

**Returns:** True if successful, False otherwise

**Example:**
```python
success = client.cancel_order("order_123")
```

#### get_balance(asset_id: Optional[str] = None) → Dict[str, float]

Get account balance.

**Parameters:**
- `asset_id`: Specific asset ID (optional)

**Returns:** Balance dictionary

**Example:**
```python
balances = client.get_balance()
usdc_balance = balances.get('USDC', 0)
```

#### get_open_orders() → List[Dict]

Get all open orders.

**Returns:** List of open order dictionaries

**Example:**
```python
orders = client.get_open_orders()
for order in orders:
    print(f"Order {order['id']}: {order['size']} @ {order['price']}")
```

#### get_positions() → List[Dict]

Get all current positions.

**Returns:** List of position dictionaries

**Example:**
```python
positions = client.get_positions()
for pos in positions:
    print(f"Position: {pos['token_id']} - {pos['size']} shares")
```

## MarketMonitor

### Overview
The `MarketMonitor` class provides market discovery and analysis capabilities.

### Initialization

```python
from src.core.market_monitor import MarketMonitor

monitor = MarketMonitor(client, config)
```

### Methods

#### discover_markets(min_liquidity: Optional[float] = None, tags: Optional[List[str]] = None) → List[Dict]

Discover active markets based on criteria.

**Parameters:**
- `min_liquidity`: Minimum liquidity requirement
- `tags`: Filter by specific tags

**Returns:** List of markets matching criteria

**Example:**
```python
markets = monitor.discover_markets(
    min_liquidity=5000,
    tags=['politics', 'sports']
)
```

#### get_market_prices(condition_id: str) → Dict[str, float]

Get current prices for all tokens in a market.

**Parameters:**
- `condition_id`: Market condition ID

**Returns:** Dictionary mapping token_id to mid price

**Example:**
```python
prices = monitor.get_market_prices("0x1234...")
for token_id, price in prices.items():
    print(f"Token {token_id}: {price:.3f}")
```

#### analyze_market_depth(token_id: str) → Dict[str, Any]

Analyze orderbook depth.

**Parameters:**
- `token_id`: Token identifier

**Returns:** Market depth analysis

**Example:**
```python
depth = monitor.analyze_market_depth("0x5678...")
print(f"Spread: {depth['spread_percentage']:.2f}%")
print(f"Bid/Ask Ratio: {depth['bid_ask_ratio']:.2f}")
```

#### track_market(condition_id: str) → None

Start tracking a specific market.

**Parameters:**
- `condition_id`: Market condition ID

**Example:**
```python
monitor.track_market("0x1234...")
```

#### find_arbitrage_opportunities() → List[Dict]

Find potential arbitrage opportunities in tracked markets.

**Returns:** List of arbitrage opportunities

**Example:**
```python
opportunities = monitor.find_arbitrage_opportunities()
for opp in opportunities:
    print(f"Arbitrage: {opp['question']}")
    print(f"Total price: {opp['total_price']:.3f}")
```

## BaseAgent

### Overview
Abstract base class for all trading agents.

### Initialization

```python
from src.agents.base_agent import BaseAgent

class MyAgent(BaseAgent):
    def analyze_market(self, market):
        # Implementation
        pass
    
    def generate_trading_signal(self, analysis):
        # Implementation
        pass

agent = MyAgent(config)
```

### Abstract Methods (Must Implement)

#### analyze_market(market: Dict[str, Any]) → Dict[str, Any]

Analyze a market and return analysis data.

**Parameters:**
- `market`: Market data dictionary

**Returns:** Analysis result dictionary

#### generate_trading_signal(analysis: Dict[str, Any]) → Optional[Dict[str, Any]]

Generate trading signal from analysis.

**Parameters:**
- `analysis`: Market analysis dictionary

**Returns:** Trading signal or None

**Signal Format:**
```python
{
    "token_id": "0x5678...",
    "side": "BUY",
    "price": 0.65,
    "size": 10,
    "reason": "Strong momentum"
}
```

### Built-in Methods

#### execute_trade(token_id: str, side: str, size: float, price: float) → Optional[Dict]

Execute a trade with risk checks.

**Parameters:**
- `token_id`: Token to trade
- `side`: "BUY" or "SELL"
- `size`: Trade size
- `price`: Trade price

**Returns:** Trade result or None

**Example:**
```python
result = agent.execute_trade(
    token_id="0x5678...",
    side="BUY",
    size=10,
    price=0.65
)
```

#### get_performance_stats() → Dict[str, Any]

Get performance statistics.

**Returns:** Performance metrics dictionary

**Example:**
```python
stats = agent.get_performance_stats()
print(f"Win Rate: {stats['win_rate']:.2%}")
print(f"Total P&L: ${stats['total_profit_loss']:.2f}")
```

#### run() → None

Main agent loop - discover, analyze, trade.

**Example:**
```python
agent.run()
```

## FeeCollector

### Overview
Handles fee collection from profitable trades.

### Initialization

```python
from src.core.fee_collector import FeeCollector

fee_collector = FeeCollector(config)
```

### Methods

#### calculate_fee(profit_amount: float) → float

Calculate fee based on profit.

**Parameters:**
- `profit_amount`: Profit in USDC

**Returns:** Fee amount

**Example:**
```python
profit = 100
fee = fee_collector.calculate_fee(profit)  # Returns 1.0 if fee_percentage=0.01
```

#### collect_fee(from_address: str, amount: float, transaction_hash: Optional[str] = None) → Dict

Record fee collection.

**Parameters:**
- `from_address`: Source address
- `amount`: Fee amount
- `transaction_hash`: Associated transaction

**Returns:** Fee collection record

**Example:**
```python
record = fee_collector.collect_fee(
    from_address="0xabc...",
    amount=1.0,
    transaction_hash="0xdef..."
)
```

#### get_total_fees() → float

Get total fees collected.

**Returns:** Total fees in USDC

**Example:**
```python
total = fee_collector.get_total_fees()
print(f"Total fees: ${total:.2f}")
```

#### get_fee_history() → List[Dict]

Get history of fee collections.

**Returns:** List of fee records

**Example:**
```python
history = fee_collector.get_fee_history()
for record in history:
    print(f"Fee: ${record['amount']} from {record['from_address']}")
```

## Configuration

### Config Class

Configuration is managed using Pydantic settings.

```python
from src.core.config import load_config, Config

# Load from .env file
config = load_config()

# Access settings
print(config.default_trade_size)
print(config.fee_percentage)

# Override programmatically
config = Config(
    default_trade_size=20,
    dry_run=False
)
```

### Available Settings

See `.env.example` for all available configuration options.

## Error Handling

All methods handle errors gracefully:

- API errors return `None` or empty collections
- Errors are logged using the logging system
- Trading errors don't crash the bot

**Example:**
```python
market = client.get_market("invalid_id")
if market is None:
    print("Market not found")
```

## Type Hints

All methods include type hints for IDE support:

```python
def get_markets(self, limit: int = 100) -> List[Dict[str, Any]]:
    ...
```

## Logging

All components use Python's logging system:

```python
import logging

logger = logging.getLogger(__name__)
logger.info("Market analyzed")
logger.error("Failed to place order")
```

Configure logging level in `.env`:
```
LOG_LEVEL=INFO
```
