# Quick Start Guide

Get your Polymarket trading bot up and running in 5 minutes!

## Prerequisites

- Python 3.8+
- Git
- Ethereum wallet with some MATIC for gas fees
- USDC on Polygon (for trading)

## Installation

### 1. Clone and Setup

```bash
# Clone repository
git clone https://github.com/LPTravelAustralia/polymarket.git
cd polymarket

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
# Copy environment template
cp .env.example .env

# Edit .env file with your credentials
nano .env  # or use your preferred editor
```

**Minimum required settings:**
```env
WALLET_PRIVATE_KEY=your_private_key_here
WALLET_ADDRESS=your_wallet_address_here
DRY_RUN=true
```

## First Steps

### Option 1: Monitor Markets (Safe - No Trading)

See what markets are available:

```bash
python scripts/monitor_markets.py
```

This will show you:
- Active markets with good liquidity
- Current prices
- Potential arbitrage opportunities

### Option 2: Test Trading Bot (Dry Run)

Test the momentum bot without real trades:

```bash
# Ensure DRY_RUN=true in .env
python scripts/run_trading_bot.py
```

Watch the bot:
- Discover markets
- Analyze momentum
- Generate signals
- Simulate trades (no real money)

Press `Ctrl+C` to stop.

### Option 3: Run Arbitrage Scanner

Find arbitrage opportunities:

```bash
python scripts/run_arbitrage_bot.py
```

## Understanding the Output

### Market Monitor Output
```
INFO: Found 42 markets with sufficient liquidity
INFO: 
1. Will Bitcoin hit $100k in 2024?
   Liquidity: $125,432.50
   Volume: $892,123.00
   Token 0x123...: 0.650
   Token 0x456...: 0.340
```

### Trading Bot Output
```
INFO: Running trading cycle...
INFO: Discovered 42 markets
INFO: Analyzing market: Will Bitcoin hit $100k?
INFO: DRY RUN: Would place BUY order for 10 shares at 0.650
INFO: Performance: {'total_trades': 0, 'win_rate': 0.0, 'total_profit_loss': 0.0}
```

## Going Live

⚠️ **Warning:** Only do this after thorough testing!

### 1. Update Configuration

Edit `.env`:
```env
DRY_RUN=false
AUTO_TRADE=true
DEFAULT_TRADE_SIZE=10  # Start small!
```

### 2. Fund Your Wallet

- Transfer USDC to your Polygon wallet
- Keep some MATIC for gas fees (~0.01 MATIC)
- Start with small amounts for testing

### 3. Run with Auto-Trading

```bash
python scripts/run_trading_bot.py
```

The bot will now execute real trades!

## Customization

### Adjust Trade Size

In `.env`:
```env
DEFAULT_TRADE_SIZE=5  # Trade 5 USDC per signal
MAX_POSITION_SIZE=100  # Max 100 USDC per position
```

### Change Monitoring Frequency

```env
MONITORING_INTERVAL=120  # Check every 2 minutes
```

### Filter by Liquidity

```env
MIN_LIQUIDITY=5000  # Only trade markets with $5k+ liquidity
```

## Enabling AI Predictions

### 1. Get API Key

- OpenAI: https://platform.openai.com/api-keys
- Or Anthropic: https://console.anthropic.com/

### 2. Configure

In `.env`:
```env
USE_AI_PREDICTIONS=true
OPENAI_API_KEY=sk-your-key-here
```

### 3. Run AI Bot

```bash
python scripts/run_ai_bot.py
```

The bot will now use GPT-4 for market analysis!

## Collecting Fees (For Bot Operators)

If you're distributing this bot to others:

### 1. Set Fee Configuration

In `.env`:
```env
FEE_PERCENTAGE=0.015  # 1.5% of profits
FEE_WALLET_ADDRESS=your_fee_collection_address
```

### 2. Distribute to Users

Users run the bot with your fee settings automatically applied.

### 3. Monitor Fee Collection

```python
from src.core.fee_collector import FeeCollector
from src.core.config import load_config

config = load_config()
collector = FeeCollector(config)

# Check collected fees
total = collector.get_total_fees()
print(f"Total fees collected: ${total:.2f}")

# View history
history = collector.get_fee_history()
for record in history:
    print(f"${record['amount']} from {record['from_address']}")
```

## Troubleshooting

### "Module not found" Error

```bash
# Make sure you're in the virtual environment
source venv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt
```

### "Failed to initialize client" Error

- Check your wallet private key is correct
- Ensure you're using the correct format (no 0x prefix needed)
- Verify your wallet has MATIC for gas

### "No markets found"

- Check your internet connection
- Polymarket API might be down
- Try adjusting MIN_LIQUIDITY setting

### "Permission denied" on Scripts

```bash
# Make scripts executable
chmod +x scripts/*.py
```

## Next Steps

### Learn More
- Read [Architecture Documentation](docs/ARCHITECTURE.md)
- Review [API Documentation](docs/API.md)
- Explore the codebase in `src/`

### Customize
- Create your own trading strategy (see docs)
- Adjust risk parameters
- Add custom indicators

### Monitor
- Check logs in `logs/` directory
- Track performance metrics
- Review trade history

## Safety Reminders

✅ **Do:**
- Start with DRY_RUN=true
- Use small trade sizes initially
- Monitor the bot regularly
- Keep backups of your config

❌ **Don't:**
- Risk more than you can afford to lose
- Run unattended until fully tested
- Share your private keys
- Commit `.env` file to git

## Getting Help

- Check the main [README](../README.md)
- Review example scripts in `scripts/`
- Open an issue on GitHub

## Resources

- [Polymarket](https://polymarket.com)
- [Polymarket Docs](https://docs.polymarket.com)
- [py-clob-client](https://github.com/Polymarket/py-clob-client)

---

**Happy Trading! 🚀**
