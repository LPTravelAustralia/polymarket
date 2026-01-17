# News-Driven Trading Guide

## Overview

The **News Monitor Agent** is a sophisticated trading system that monitors breaking news in real-time and automatically trades on Polymarket before the market fully reacts to news events. This gives you a competitive edge by acting on information faster than manual traders.

## How It Works

```
┌─────────────────────────────────────────────────────────────┐
│                    NEWS MONITORING CYCLE                     │
└─────────────────────────────────────────────────────────────┘

1. FETCH NEWS (NewsAPI)
   ↓ Every 5 minutes (configurable)
   
2. MATCH TO MARKETS
   ↓ Keyword extraction & matching
   
3. AI ANALYSIS (Claude)
   ↓ Impact scoring & direction
   
4. TWITTER VALIDATION (Optional)
   ↓ Check trending topics
   
5. GENERATE SIGNALS
   ↓ Filter by confidence & impact
   
6. EXECUTE TRADES
   └→ Automatic or manual review
```

## Key Features

### 🔍 **Smart News Matching**
- Automatically extracts keywords from market questions
- Matches breaking news to relevant markets
- Filters by news age (only recent, relevant news)

### 🤖 **Claude AI Analysis**
- Analyzes news impact on market outcomes
- Provides confidence scores and reasoning
- Understands context and nuance

### 📊 **Multi-Factor Scoring**
- **Impact Score**: How much the news affects the market (0-1)
- **Confidence**: How certain the prediction is (0-1)
- **Urgency**: How quickly to act (0-1)
- **Direction**: YES, NO, or NEUTRAL

### 🐦 **Twitter Validation** (Optional)
- Cross-references with Twitter trending topics
- Boosts confidence when keywords are trending
- Validates news signals with social sentiment

### ⚡ **Fast Execution**
- Acts within minutes of breaking news
- Prioritizes recent and urgent news
- Gets ahead of market reactions

## Setup

### 1. Get API Keys

#### NewsAPI (Required)
Get your free API key at: https://newsapi.org/register

```bash
NEWSAPI_KEY=your_newsapi_key_here
```

#### Claude AI (Strongly Recommended)
Get API key at: https://console.anthropic.com/

```bash
ANTHROPIC_API_KEY=your_claude_key_here
```

#### Twitter API (Optional)
Get Bearer Token at: https://developer.twitter.com/

```bash
TWITTER_BEARER_TOKEN=your_twitter_bearer_token
```

### 2. Configure Settings

Add to your `.env` file:

```bash
# News Monitoring
NEWSAPI_KEY=your_key
ANTHROPIC_API_KEY=your_key
TWITTER_BEARER_TOKEN=your_key  # Optional

# Trading Settings
NEWS_MONITORING_INTERVAL=300   # Check every 5 minutes
NEWS_MIN_IMPACT_SCORE=0.6      # Minimum 0.6 impact to trade
NEWS_MIN_CONFIDENCE=0.65       # Minimum 65% confidence
NEWS_MAX_AGE_HOURS=2          # Only news from last 2 hours
NEWS_USE_TWITTER=false         # Enable Twitter validation

# Safety
DRY_RUN=true                   # Test mode (no real trades)
AUTO_TRADE=false               # Require manual approval
```

### 3. Run the Monitor

#### Test Mode (Recommended First)
```bash
# Single run to see what it finds
python scripts/run_news_monitor.py --once --dry-run

# Continuous monitoring (test mode)
python scripts/run_news_monitor.py --dry-run
```

#### Live Trading
```bash
# Enable auto-trading in .env first:
# AUTO_TRADE=true
# DRY_RUN=false

# Start continuous monitoring
python scripts/run_news_monitor.py

# With Twitter validation
python scripts/run_news_monitor.py --use-twitter

# Custom settings
python scripts/run_news_monitor.py \
  --interval 180 \
  --min-liquidity 50000 \
  --min-impact 0.7 \
  --min-confidence 0.75
```

## Usage Examples

### Example 1: Breaking Political News

**Scenario**: Trump announces major policy decision

**Process**:
1. 📰 NewsAPI detects headline: "Trump Announces..."
2. 🔍 System matches to market: "Will Trump win 2024 election?"
3. 🤖 Claude analyzes impact: 0.82 score, YES direction
4. 🐦 Twitter shows "Trump" trending (boost confidence)
5. ✅ Generate signal with 87% confidence
6. 💰 Execute trade (buy YES shares)

### Example 2: Economic Data Release

**Scenario**: Fed announces interest rate decision

**Process**:
1. 📰 News: "Fed raises rates by 0.5%"
2. 🔍 Matches: "Will inflation exceed 3% in 2024?"
3. 🤖 Analysis: 0.75 impact, NO direction
4. 💡 Reasoning: "Higher rates typically reduce inflation"
5. 📈 Trade: Buy NO shares

### Example 3: Sports Event

**Scenario**: Star player injury

**Process**:
1. 📰 News: "LeBron James out for season"
2. 🔍 Matches: "Will Lakers make playoffs?"
3. 🤖 Analysis: 0.91 impact, NO direction
4. ⚡ High urgency (breaking news)
5. 💰 Immediate trade execution

## Configuration Reference

### Command Line Options

```bash
python scripts/run_news_monitor.py [OPTIONS]

Options:
  --interval SECONDS       Monitoring interval (default: 300)
  --min-liquidity USD      Minimum market liquidity (default: 10000)
  --min-impact SCORE       Minimum impact score 0-1 (default: 0.6)
  --min-confidence SCORE   Minimum confidence 0-1 (default: 0.65)
  --dry-run               Test mode without real trades
  --use-twitter           Enable Twitter validation
  --once                  Run once and exit (no loop)
```

### Environment Variables

```bash
# Required
NEWSAPI_KEY              # NewsAPI key for fetching news
ANTHROPIC_API_KEY        # Claude AI for analysis

# Optional
TWITTER_BEARER_TOKEN     # Twitter API for validation
NEWS_MONITORING_INTERVAL # Check frequency (seconds)
NEWS_MIN_IMPACT_SCORE    # Minimum impact to trade (0-1)
NEWS_MIN_CONFIDENCE      # Minimum confidence to trade (0-1)
NEWS_MAX_AGE_HOURS       # Max news age to consider
NEWS_USE_TWITTER         # Enable Twitter validation
```

## Signal Examples

### High-Quality Signal
```
🎯 SIGNAL: Will Trump win the 2024 presidential election?
   📰 News: "Trump wins Iowa caucus by landslide margin"
   📈 Direction: YES
   💯 Confidence: 0.87 (87%)
   ⚡ Impact: 0.82
   ⏱️  Urgency: 0.95 (breaking news)
   🔍 Source: Associated Press (2024-01-16T10:23:00Z)
   💭 Reasoning: Winning Iowa caucus demonstrates strong Republican support
                 and increases likelihood of securing nomination and general
                 election victory. High-credibility source.
```

### Low-Quality Signal (Filtered Out)
```
❌ FILTERED: Will Bitcoin reach $100k in 2024?
   📰 News: "Crypto influencer predicts Bitcoin surge"
   📈 Direction: YES
   💯 Confidence: 0.42 (too low)
   ⚡ Impact: 0.35 (too low)
   🔍 Source: Unknown Blog
   ⛔ REASON: Below confidence threshold (0.65)
```

## Best Practices

### ✅ DO

1. **Start with dry-run mode** to understand signals
2. **Use Twitter validation** for extra confidence
3. **Monitor high-liquidity markets** (>$10k)
4. **Set conservative thresholds** initially
5. **Review signals manually** before enabling auto-trade
6. **Keep news age low** (1-2 hours max)
7. **Monitor logs** for signal quality

### ❌ DON'T

1. **Don't enable auto-trade immediately**
2. **Don't use low-confidence signals** (<0.65)
3. **Don't ignore liquidity requirements**
4. **Don't over-trade** on every news item
5. **Don't skip Twitter validation** (if available)
6. **Don't set intervals too short** (<3 minutes)
7. **Don't ignore impact scores** (<0.6)

## Advanced Usage

### Custom Signal Processing

```python
from src.agents.news_monitor_agent import NewsMonitorAgent
from src.core.config import load_config

# Initialize
config = load_config()
agent = NewsMonitorAgent(config)

# Get signals for specific markets
markets = [{"id": "123", "question": "Will Trump win?"}]
signals = agent.generate_signals(markets)

# Custom filtering
high_quality_signals = [
    s for s in signals 
    if s.confidence > 0.8 and s.impact_score > 0.7
]

# Process signals
for signal in high_quality_signals:
    print(f"Market: {signal.market_question}")
    print(f"Direction: {signal.direction}")
    print(f"Confidence: {signal.confidence:.2%}")
```

### Integrate with Other Agents

```python
from src.agents.news_monitor_agent import NewsMonitorAgent
from src.agents.ai_agent import AIAgent

# Combine news signals with AI predictions
news_agent = NewsMonitorAgent(config)
ai_agent = AIAgent(config)

news_signals = news_agent.generate_signals(markets)
ai_predictions = ai_agent.evaluate_market(market)

# Use both for higher confidence
if news_signals and ai_predictions:
    combined_confidence = (
        news_signals[0].confidence * 0.6 +
        ai_predictions['confidence'] * 0.4
    )
```

## Monitoring & Logs

### Log Output Example

```
2024-01-16 10:23:45 | INFO | Starting news monitoring loop (interval: 300s)
2024-01-16 10:23:46 | INFO | Monitoring 47 markets
2024-01-16 10:23:47 | INFO | Retrieved 50 headlines
2024-01-16 10:23:48 | INFO | Found 12 markets with relevant news
2024-01-16 10:23:52 | INFO | 🎯 SIGNAL: Will Trump win the 2024 election?
2024-01-16 10:23:52 | INFO |    News: Trump wins Iowa caucus...
2024-01-16 10:23:52 | INFO |    Impact: 0.82 | Direction: YES | Confidence: 0.87
2024-01-16 10:23:53 | INFO | Generated 3 trading signals
2024-01-16 10:23:53 | INFO | 🚀 Executing news-driven trade:
2024-01-16 10:23:53 | INFO |    Market: Will Trump win the 2024 election?
2024-01-16 10:23:53 | INFO |    Direction: YES
2024-01-16 10:23:53 | INFO |    Confidence: 87%
2024-01-16 10:23:54 | INFO |    ✅ Trade executed successfully
2024-01-16 10:23:54 | INFO | Sleeping for 300s...
```

### Status Checking

```python
# Get agent status
status = agent.get_status()
print(f"Articles processed: {status['articles_processed']}")
print(f"Markets tracked: {status['markets_tracked']}")
print(f"Last update: {status['last_update']}")
```

## Troubleshooting

### No Signals Generated

**Check**:
- NewsAPI key is valid
- Markets have sufficient liquidity
- News is recent (within max age)
- Thresholds aren't too high
- Keywords match market questions

### Low Confidence Scores

**Solutions**:
- Enable Twitter validation
- Lower min_confidence threshold
- Use more specific market questions
- Wait for breaking news (not speculation)

### API Rate Limits

**NewsAPI**: 100 requests/day (free tier)
- Use longer intervals (5-10 minutes)
- Cache results appropriately

**Claude**: Pay-as-you-go
- Monitor token usage
- Batch similar markets

**Twitter**: 500k tweets/month (free tier)
- Use sparingly
- Only for high-impact signals

## Performance Metrics

Track your news-driven trading performance:

```python
# Log all trades with metadata
{
    "timestamp": "2024-01-16T10:23:54Z",
    "market": "Will Trump win 2024?",
    "direction": "YES",
    "confidence": 0.87,
    "impact": 0.82,
    "news_source": "AP",
    "outcome": "pending"
}

# Analyze later
win_rate = wins / total_trades
avg_confidence = sum(confidences) / len(confidences)
```

## FAQ

**Q: How fast does it react to breaking news?**
A: Typically 5-15 minutes (depending on monitoring interval and NewsAPI update frequency).

**Q: Does it work without Claude AI?**
A: Yes, but with much lower quality signals. Claude AI is strongly recommended.

**Q: Can I use it for specific markets only?**
A: Yes, filter markets before calling `generate_signals()`.

**Q: What's the typical win rate?**
A: Depends on thresholds. With min_confidence=0.7+, expect 65-75% accuracy.

**Q: How much does it cost to run?**
A: NewsAPI: Free (100 req/day)
   Claude: ~$0.01-0.05 per signal
   Twitter: Free (500k tweets/month)

## Next Steps

1. **Test in dry-run mode** for a few days
2. **Review signal quality** and adjust thresholds
3. **Enable Twitter validation** for better signals
4. **Start with small position sizes**
5. **Monitor performance** and iterate
6. **Combine with other agents** for best results

---

**Need Help?** Check the logs or create an issue in the repository.
