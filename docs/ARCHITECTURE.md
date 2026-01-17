# Architecture Documentation

## Overview

The Polymarket Trading Bot is designed with a modular architecture that separates concerns into distinct layers:

1. **Core Layer**: Fundamental functionality for API interaction, configuration, and monitoring
2. **Agent Layer**: Trading strategies and decision-making logic
3. **Utility Layer**: Supporting functions for logging, data processing, etc.
4. **Script Layer**: Entry points and example implementations

## Component Details

### Core Layer

#### PolymarketClient (`src/core/client.py`)

**Purpose**: Wrapper around py-clob-client for Polymarket API operations

**Key Methods**:
- `get_markets()`: Fetch available markets
- `get_orderbook()`: Get bid/ask orders for a token
- `place_order()`: Execute buy/sell orders
- `get_balance()`: Check account balance
- `get_positions()`: View current positions

**Design Decisions**:
- Encapsulates all API calls in one place
- Handles error logging and recovery
- Supports dry-run mode for testing
- Uses py-clob-client as underlying library

#### MarketMonitor (`src/core/market_monitor.py`)

**Purpose**: Market discovery and analysis

**Key Features**:
- Filter markets by liquidity
- Track market prices in real-time
- Analyze orderbook depth
- Detect arbitrage opportunities

**Usage Pattern**:
```python
monitor = MarketMonitor(client, config)
markets = monitor.discover_markets(min_liquidity=1000)
prices = monitor.get_market_prices(condition_id)
depth = monitor.analyze_market_depth(token_id)
```

#### FeeCollector (`src/core/fee_collector.py`)

**Purpose**: Handle fee collection from profitable trades

**Features**:
- Calculate fees based on profits
- Track fee history
- Record fee transactions
- Support for Web3 transfers (planned)

**Fee Model**:
- Performance-based (only on profits)
- Configurable percentage
- Transparent tracking
- Automated collection

### Agent Layer

#### BaseAgent (`src/agents/base_agent.py`)

**Purpose**: Abstract base class for all trading agents

**Core Methods** (must implement):
- `analyze_market()`: Analyze market data
- `generate_trading_signal()`: Create trading signals

**Built-in Features**:
- Risk management
- Trade execution
- Performance tracking
- Fee collection integration

**Lifecycle**:
```
Initialize → Discover Markets → Analyze → Generate Signals → Execute → Track Performance
```

#### MomentumAgent (`src/agents/momentum_agent.py`)

**Strategy**: Trade based on order flow momentum

**Indicators**:
- Bid/ask volume ratio
- Spread percentage
- Momentum score calculation

**Entry Criteria**:
- Momentum score > 1.5
- Spread < 5%
- Within risk limits

#### ArbitrageAgent (`src/agents/arbitrage_agent.py`)

**Strategy**: Exploit mispriced markets

**Detection**:
- Binary markets where sum(prices) ≠ 1
- Minimum 2% margin required

**Execution**:
- Buy all outcomes for guaranteed profit
- Risk-free if executed atomically

#### AIAgent (`src/agents/ai_agent.py`)

**Strategy**: Use LLMs for prediction

**Workflow**:
1. Fetch market data
2. Create prediction prompt
3. Get AI prediction with probabilities
4. Compare AI prediction vs market price
5. Trade if edge > 10% and confidence > 70%

**Supported Models**:
- OpenAI GPT-4
- Anthropic Claude
- Extensible to other providers

## Data Flow

### Market Discovery Flow

```
MarketMonitor.discover_markets()
    ↓
Filter by liquidity, tags, status
    ↓
Return filtered market list
```

### Trading Flow

```
Agent.run()
    ↓
Discover markets
    ↓
For each market:
    → analyze_market()
    → generate_trading_signal()
    → If signal: execute_trade()
        → Check risk limits
        → Place order via PolymarketClient
        → Calculate fees
        → Record trade
    ↓
Track performance
```

### Fee Collection Flow

```
Execute SELL order
    ↓
Calculate profit
    ↓
If profit > 0:
    → Calculate fee (profit × fee_percentage)
    → Record fee transaction
    → Update total fees
```

## Configuration Management

The bot uses Pydantic for type-safe configuration management:

```python
class Config(BaseSettings):
    # Load from environment variables
    # Validate types
    # Provide defaults
    # Support .env files
```

**Benefits**:
- Type validation
- Default values
- Environment variable support
- Easy testing with override

## Error Handling Strategy

1. **API Errors**: Log and return None/empty list
2. **Trading Errors**: Log, skip trade, continue
3. **Fatal Errors**: Log and re-raise
4. **Validation Errors**: Caught at config load time

## Security Considerations

### Private Key Management
- Store in `.env` file
- Never commit to git
- Use environment variables in production

### API Key Protection
- Separate API keys per environment
- Rotate regularly
- Limit permissions

### Trade Safety
- Dry-run mode by default
- Position size limits
- Risk percentage controls
- Manual approval option

## Performance Considerations

### Optimization Strategies

1. **API Calls**: 
   - Cache market data when appropriate
   - Batch requests where possible
   - Rate limit awareness

2. **Market Scanning**:
   - Filter early (liquidity, status)
   - Track only relevant markets
   - Periodic refresh (configurable interval)

3. **Risk Calculations**:
   - Pre-compute limits
   - Cache balance checks
   - Efficient position tracking

## Extensibility

### Adding New Strategies

1. Create new agent class inheriting from `BaseAgent`
2. Implement `analyze_market()` method
3. Implement `generate_trading_signal()` method
4. Add configuration options if needed
5. Create script in `scripts/` folder

Example:
```python
class MyStrategy(BaseAgent):
    def analyze_market(self, market):
        # Your analysis logic
        return analysis
    
    def generate_trading_signal(self, analysis):
        # Your signal logic
        return signal
```

### Adding New Indicators

Add methods to `MarketMonitor`:
```python
def calculate_custom_indicator(self, token_id):
    # Fetch data
    # Calculate indicator
    # Return value
```

### Adding AI Providers

Update `AIAgent._initialize_llm()`:
```python
elif self.config.custom_api_key:
    from custom_provider import Client
    self.llm_client = Client(api_key=...)
```

## Testing Strategy

### Unit Tests
- Test individual components
- Mock external dependencies
- Test edge cases

### Integration Tests
- Test component interactions
- Use testnet
- Verify end-to-end flows

### Dry-Run Testing
- Test with real market data
- No actual trades
- Verify logic and risk management

## Monitoring & Logging

### Log Levels
- **DEBUG**: Detailed execution info
- **INFO**: Trade executions, performance
- **WARNING**: Risk limit breaches, API issues
- **ERROR**: Failed trades, exceptions

### Key Metrics
- Total trades
- Win rate
- Profit/loss
- Fees collected
- API success rate

## Deployment Options

### Local Development
- Virtual environment
- `.env` file for config
- Manual execution

### Server Deployment
- Systemd service
- Supervisor process manager
- Cronjob scheduling

### Container Deployment
- Docker container
- Kubernetes pod
- Cloud Run / AWS ECS

### Monitoring
- Log aggregation (e.g., ELK stack)
- Alerting (e.g., PagerDuty)
- Metrics (e.g., Prometheus)

## Future Enhancements

### Planned Features
1. **Web Dashboard**: Real-time monitoring UI
2. **Backtesting**: Historical simulation framework
3. **Advanced Analytics**: Performance analysis tools
4. **Multi-Agent**: Coordinate multiple strategies
5. **Portfolio Optimization**: Kelly criterion, etc.

### Research Areas
- Machine learning models
- Sentiment analysis
- News integration
- Cross-market analysis
- Order routing optimization
