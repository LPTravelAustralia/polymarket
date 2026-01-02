# Polymarket Trading Bot

A comprehensive Python-based trading bot for Polymarket with AI-powered predictions, automated trading strategies, and fee collection mechanism.

## 🚀 Live Demo

**Frontend:** https://boisterous-basbousa-e11b8a.netlify.app/

**Backend API:** http://136.114.57.247:8000/docs

The bot is currently running in **paper trading mode** (simulated trades, no real money).

## Current Status (January 2, 2026)

| Component | Status |
|-----------|--------|
| Frontend UI | ✅ Live on Netlify |
| Backend API | ✅ Running on GCloud VM |
| 6 Trading Strategies | ✅ All Working |
| Category Filtering | ✅ Working (10 categories) |
| Kelly Criterion Sizing | ✅ Working |
| Paper Trading | ✅ Working |
| Live Trading | 🔴 Not enabled (needs wallet keys) |

See [SETUP_REFERENCE.md](SETUP_REFERENCE.md) for detailed deployment info and TODO list.

## Features

- 🤖 **Multiple Trading Strategies**
  - Momentum-based trading
  - Value (mean reversion)
  - Arbitrage detection
  - Combined (multi-signal weighted)
  - AI-powered predictions using GPT-4 or Claude
  - News sentiment analysis

- 💰 **Fee Collection System**
  - Configurable performance-based fees
  - Automatic fee calculation on profitable trades
  - Fee wallet management

- 📊 **Market Analysis**
  - Real-time market monitoring
  - Orderbook depth analysis
  - Liquidity filtering
  - Price tracking

- 🛡️ **Risk Management**
  - Kelly Criterion position sizing
  - Position size limits
  - Portfolio percentage controls
  - Take profit / Stop loss
  - Category filtering
  - Spread filtering
  - Dry-run mode for testing

- 📈 **Performance Tracking**
  - Trade history
  - Win rate calculation
  - Profit/loss tracking
  - Fee collection reports

## Architecture

```
polymarket/
├── src/
│   ├── agents/          # Trading agent implementations
│   │   ├── base_agent.py        # Base agent class
│   │   ├── momentum_agent.py    # Momentum strategy
│   │   ├── arbitrage_agent.py   # Arbitrage strategy
│   │   └── ai_agent.py          # AI-powered strategy
│   ├── core/            # Core functionality
│   │   ├── client.py            # Polymarket API wrapper
│   │   ├── config.py            # Configuration management
│   │   ├── market_monitor.py    # Market discovery & monitoring
│   │   └── fee_collector.py     # Fee collection system
│   └── utils/           # Utility functions
│       └── logging_utils.py     # Logging setup
├── scripts/             # Example scripts
│   ├── run_trading_bot.py       # Simple momentum bot
│   ├── run_arbitrage_bot.py     # Arbitrage bot
│   ├── run_ai_bot.py            # AI prediction bot
│   └── monitor_markets.py       # Market monitoring
├── docs/                # Documentation
├── tests/               # Test suite
├── requirements.txt     # Python dependencies
├── .env.example         # Environment template
└── README.md           # This file
```

## Installation

### Prerequisites

- Python 3.8 or higher
- Polygon wallet with USDC
- Polymarket API credentials (optional for read-only)
- OpenAI or Anthropic API key (for AI agent)

### Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/LPTravelAustralia/polymarket.git
   cd polymarket
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your credentials
   ```

## Configuration

Edit the `.env` file with your settings:

### Required Settings
- `WALLET_PRIVATE_KEY`: Your Ethereum private key
- `WALLET_ADDRESS`: Your Ethereum address

### Optional Settings
- `POLYMARKET_API_KEY`: Polymarket API key (for advanced features)
- `OPENAI_API_KEY`: OpenAI API key (for AI predictions)
- `ANTHROPIC_API_KEY`: Anthropic API key (alternative AI provider)

### Trading Settings
- `DEFAULT_TRADE_SIZE`: Default trade size in USDC (default: 10)
- `MAX_POSITION_SIZE`: Maximum position size (default: 1000)
- `RISK_PERCENTAGE`: Max risk per trade as % of portfolio (default: 0.02)
- `MIN_LIQUIDITY`: Minimum market liquidity filter (default: 1000)

### Fee Settings
- `FEE_PERCENTAGE`: Fee percentage on profits (default: 0.01 = 1%)
- `FEE_WALLET_ADDRESS`: Wallet address for fee collection

### Bot Settings
- `BOT_MODE`: "mainnet" or "testnet" (default: "testnet")
- `DRY_RUN`: Test mode without real trades (default: true)
- `AUTO_TRADE`: Enable automatic trading (default: false)
- `MONITORING_INTERVAL`: Seconds between trading cycles (default: 60)

## Usage

### 1. Market Monitoring

Monitor active markets and check for opportunities:

```bash
python scripts/monitor_markets.py
```

This will:
- List active markets with sufficient liquidity
- Display current prices
- Check for arbitrage opportunities

### 2. Simple Trading Bot (Momentum Strategy)

Run a momentum-based trading bot:

```bash
python scripts/run_trading_bot.py
```

This bot:
- Analyzes market momentum using bid/ask ratios
- Executes trades on strong momentum signals
- Manages risk and position sizing

### 3. Arbitrage Bot

Run an arbitrage detection and execution bot:

```bash
python scripts/run_arbitrage_bot.py
```

This bot:
- Scans for arbitrage opportunities
- Detects mispriced markets
- Executes guaranteed profit trades

### 4. AI Prediction Bot

Run an AI-powered prediction bot:

```bash
python scripts/run_ai_bot.py
```

This bot:
- Uses GPT-4 or Claude for market analysis
- Generates probability predictions
- Trades on high-confidence predictions with edge

**Note:** Requires `USE_AI_PREDICTIONS=true` and valid API key in `.env`

## Fee Collection Model

The bot includes a built-in fee collection mechanism for monetizing bot usage:

### How It Works

1. **Performance-Based Fees**: Fees are only charged on profitable trades
2. **Configurable Rate**: Set `FEE_PERCENTAGE` in config (default: 1%)
3. **Automatic Collection**: Fees are calculated and recorded automatically
4. **Transparent Tracking**: Full fee history and reporting

### For Bot Operators

To collect fees from users:

1. Set your `FEE_WALLET_ADDRESS` in the config
2. Set appropriate `FEE_PERCENTAGE` (recommend 1-2%)
3. Distribute the bot to users with your config
4. Fees are collected automatically on profitable trades

### For Bot Users

- Fees are only charged when you make profit
- Fee percentage is transparent in config
- No hidden costs
- You maintain custody of your funds

## Trading Strategies

### Momentum Strategy

Analyzes:
- Bid/ask volume ratio
- Order book depth
- Price spread

Trades when:
- Strong directional momentum detected
- Spread is reasonable (<5%)
- Risk limits are met

### Arbitrage Strategy

Detects:
- Binary markets where probabilities don't sum to 1
- Underpriced market opportunities

Executes:
- Buy all outcomes for guaranteed profit
- Only when margin > 2%

### AI Strategy

Uses:
- Large Language Models (GPT-4, Claude)
- Market analysis and reasoning
- Probability estimation

Trades when:
- AI prediction differs from market by >10%
- Confidence level > 70%
- Risk parameters met

## Risk Management

The bot includes multiple risk controls:

1. **Position Sizing**: Limits max position size
2. **Portfolio Risk**: Limits risk per trade as % of portfolio
3. **Spread Filtering**: Avoids illiquid markets with wide spreads
4. **Dry-Run Mode**: Test strategies without real money
5. **Manual Override**: Auto-trade can be disabled

## API Reference

### PolymarketClient

```python
from src.core.client import PolymarketClient
from src.core.config import load_config

config = load_config()
client = PolymarketClient(config)

# Get markets
markets = client.get_markets(limit=100)

# Get orderbook
orderbook = client.get_orderbook(token_id)

# Place order
result = client.place_order(
    token_id="0x123...",
    side="BUY",
    price=0.65,
    size=10
)
```

### Creating Custom Agents

```python
from src.agents.base_agent import BaseAgent

class MyCustomAgent(BaseAgent):
    def analyze_market(self, market):
        # Your analysis logic
        return analysis
    
    def generate_trading_signal(self, analysis):
        # Your signal generation logic
        return signal

# Use your agent
agent = MyCustomAgent(config)
agent.run()
```

## Development

### Running Tests

```bash
pytest tests/
```

### Code Style

```bash
# Format code
black src/ tests/

# Lint code
flake8 src/ tests/
```

## Deployment

### Docker (Optional)

A Dockerfile can be created for containerized deployment:

```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["python", "scripts/run_trading_bot.py"]
```

### Production Considerations

1. **Security**: Never commit `.env` file with real credentials
2. **Monitoring**: Set up logging and alerting
3. **Backups**: Regularly backup trade history and positions
4. **Updates**: Keep dependencies updated for security
5. **Testing**: Always test in dry-run mode first

## Safety & Disclaimers

⚠️ **Important Warnings:**

- **Financial Risk**: Trading prediction markets involves financial risk
- **No Guarantees**: Past performance does not guarantee future results
- **Test First**: Always use dry-run mode before live trading
- **Start Small**: Begin with small position sizes
- **Do Your Research**: Understand markets before trading
- **Legal Compliance**: Ensure compliance with local regulations

This bot is provided as-is for educational purposes. Use at your own risk.

## Support & Contributing

### Getting Help

- Check documentation in `/docs` folder
- Review example scripts in `/scripts` folder
- Open an issue for bugs or questions

### Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Add tests for new features
4. Submit a pull request

## License

MIT License - See LICENSE file for details

## Acknowledgments

- Built on top of Polymarket's py-clob-client
- Inspired by the Polymarket/agents repository
- Uses OpenAI and Anthropic for AI predictions

## Resources

- [Polymarket API Documentation](https://docs.polymarket.com)
- [Polymarket Agents Repository](https://github.com/Polymarket/agents)
- [py-clob-client](https://github.com/Polymarket/py-clob-client)
- [Polygon Network](https://polygon.technology/)

## Roadmap

Future enhancements:

- [ ] Web dashboard for monitoring
- [ ] Backtesting framework
- [ ] More trading strategies
- [ ] Advanced AI models
- [ ] Multi-market coordination
- [ ] Risk analytics dashboard
- [ ] Mobile notifications
- [ ] Portfolio optimization

---

**Built with ❤️ for the Polymarket community**
