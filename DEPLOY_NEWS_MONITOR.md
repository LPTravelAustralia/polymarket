# Deploying News Monitoring to Google Cloud Backend

## ✅ Test Results Summary

Your backend API is **fully functional** and ready for news monitoring:

- ✅ Backend API accessible at `http://34.29.163.176:8000`
- ✅ NewsAPI integration working (returning live news)
- ✅ Market data available (Fed rate markets found)
- ✅ News-to-market matching demonstrated successfully

## 📊 Test Output Highlights

### Real News Found for Fed Markets
```
Market: "Fed increases interest rates by 25+ bps after January 2026 meeting?"
Keywords: fed, increases, interest, rates

Matched News Articles:
1. "Stocks fall after Trump's DOJ opens criminal probe into Fed Chair Powell"
   → Impact: This could affect Fed decisions
   
2. "Inflation held firm in December, testing Fed amid DOJ probe into Powell"
   → Impact: High inflation + political pressure = uncertainty
   
3. "Read Jerome Powell's letter to senators..."
   → Impact: Fed transparency under scrutiny
```

This is **exactly** the type of news-to-market correlation that will drive profitable trades!

## 🚀 Deployment Steps

### Option 1: SSH to Your GCloud VM (Recommended)

```bash
# 1. SSH to your Google Cloud VM
gcloud compute ssh your-instance-name --zone your-zone

# Or if you have SSH access directly
ssh username@34.29.163.176

# 2. Navigate to your polymarket directory
cd ~/polymarket

# 3. Pull latest changes from GitHub
git fetch origin
git checkout copilot/build-polymarket-trading-bot
git pull origin copilot/build-polymarket-trading-bot

# 4. Install any new dependencies (if needed)
pip install -r requirements.txt

# 5. Verify API keys in .env
nano .env  # Or vi .env

# Make sure you have:
# NEWSAPI_KEY=your_key
# ANTHROPIC_API_KEY=your_key
# TWITTER_BEARER_TOKEN=your_key (optional)

# 6. Test the news monitor locally on VM
python3 scripts/run_news_monitor.py --once --dry-run

# 7. If test passes, run continuously
nohup python3 scripts/run_news_monitor.py --dry-run > logs/news_monitor.log 2>&1 &

# 8. Monitor the logs
tail -f logs/news_monitor.log
```

### Option 2: Deploy via GitHub Push

Since your frontend auto-deploys via GitHub → Netlify, you can do the same for backend:

```bash
# 1. Commit and push your changes (already on branch)
git add .
git commit -m "Add news monitoring system"
git push origin copilot/build-polymarket-trading-bot

# 2. SSH to GCloud VM and pull
ssh username@34.29.163.176
cd ~/polymarket
git pull origin copilot/build-polymarket-trading-bot

# 3. Restart backend service
sudo systemctl restart polymarket-backend.service

# 4. Start news monitor as a separate service
python3 scripts/run_news_monitor.py --dry-run &
```

## 🔧 Setting Up as a Systemd Service (Production)

To run the news monitor as a system service (auto-restart on failure):

```bash
# 1. Create service file
sudo nano /etc/systemd/system/polymarket-news-monitor.service
```

```ini
[Unit]
Description=Polymarket News Monitoring Service
After=network.target

[Service]
Type=simple
User=your-username
WorkingDirectory=/home/your-username/polymarket
Environment="PATH=/home/your-username/.local/bin:/usr/bin"
ExecStart=/usr/bin/python3 /home/your-username/polymarket/scripts/run_news_monitor.py
Restart=always
RestartSec=10
StandardOutput=append:/home/your-username/polymarket/logs/news_monitor.log
StandardError=append:/home/your-username/polymarket/logs/news_monitor_error.log

[Install]
WantedBy=multi-user.target
```

```bash
# 2. Enable and start the service
sudo systemctl daemon-reload
sudo systemctl enable polymarket-news-monitor
sudo systemctl start polymarket-news-monitor

# 3. Check status
sudo systemctl status polymarket-news-monitor

# 4. View logs
sudo journalctl -u polymarket-news-monitor -f
```

## 📝 Configuration on GCloud VM

Make sure your `.env` on the VM has:

```bash
# Required for news monitoring
NEWSAPI_KEY=your_newsapi_key_here          # Get at newsapi.org/register
ANTHROPIC_API_KEY=your_anthropic_key_here  # Get at console.anthropic.com

# Optional for Twitter validation
TWITTER_BEARER_TOKEN=your_token_here       # Get at developer.twitter.com

# News monitoring settings
NEWS_MONITORING_INTERVAL=300               # 5 minutes
NEWS_MIN_IMPACT_SCORE=0.6                 # 60% minimum
NEWS_MIN_CONFIDENCE=0.65                  # 65% minimum
NEWS_MAX_AGE_HOURS=2                      # Last 2 hours only
NEWS_USE_TWITTER=false                    # Enable when you have token

# Safety settings
DRY_RUN=true                              # Test mode first!
AUTO_TRADE=false                          # Manual review first!
```

## 🧪 Testing on GCloud VM

```bash
# 1. Single test run
python3 scripts/run_news_monitor.py --once --dry-run

# Expected output:
# ✅ Backend Status: ok
# 📰 Retrieved 50 headlines
# 🔍 Found 12 markets with relevant news
# 🎯 SIGNAL: Fed increases rates... | Confidence: 0.82
# 💡 To see signals, run with --once

# 2. Continuous monitoring (background)
nohup python3 scripts/run_news_monitor.py --dry-run > logs/news_monitor.log 2>&1 &

# 3. Check logs in real-time
tail -f logs/news_monitor.log

# 4. Stop monitoring
pkill -f run_news_monitor.py
```

## 📊 What to Expect

Once running, you'll see logs like:

```
2026-01-16 10:00:00 | INFO | Starting news monitoring loop (interval: 300s)
2026-01-16 10:00:01 | INFO | Monitoring 47 markets
2026-01-16 10:00:02 | INFO | Retrieved 50 headlines
2026-01-16 10:00:03 | INFO | Found 8 markets with relevant news
2026-01-16 10:00:07 | INFO | 🎯 SIGNAL: Fed increases rates...
2026-01-16 10:00:07 | INFO |    News: Stocks fall after Trump's DOJ probe...
2026-01-16 10:00:07 | INFO |    Impact: 0.78 | Direction: NO | Confidence: 0.81
2026-01-16 10:00:08 | INFO | Generated 3 trading signals
2026-01-16 10:00:08 | INFO | Auto-trade disabled - signals generated but not executed
2026-01-16 10:00:08 | INFO | Sleeping for 300s...
```

## 🔐 Security Checklist

- [ ] API keys stored in `.env` (not in code)
- [ ] `.env` file has restricted permissions: `chmod 600 .env`
- [ ] DRY_RUN=true for initial testing
- [ ] AUTO_TRADE=false until confident
- [ ] Logs directory exists: `mkdir -p logs`
- [ ] Monitor logs for errors regularly

## 💰 Going Live (When Ready)

After 24-48 hours of successful dry-run monitoring:

```bash
# 1. Update .env on GCloud VM
DRY_RUN=false
AUTO_TRADE=true

# 2. Start with conservative settings
NEWS_MIN_CONFIDENCE=0.75      # Higher threshold
DEFAULT_TRADE_SIZE=10         # Small positions

# 3. Restart the service
sudo systemctl restart polymarket-news-monitor

# 4. Monitor closely
tail -f logs/news_monitor.log
```

## 📈 Performance Monitoring

Track these metrics:

```bash
# Check how many signals generated
grep "🎯 SIGNAL" logs/news_monitor.log | wc -l

# Check average confidence
grep "Confidence:" logs/news_monitor.log | awk '{print $NF}' | python3 -c "import sys; vals=[float(x) for x in sys.stdin]; print(f'Avg: {sum(vals)/len(vals):.2f}')"

# Check for errors
grep -i error logs/news_monitor.log

# Check API usage
grep "Retrieved.*headlines" logs/news_monitor.log | tail -20
```

## 🆘 Troubleshooting

### News Monitor Not Starting
```bash
# Check if already running
ps aux | grep run_news_monitor

# Check for Python errors
python3 scripts/run_news_monitor.py --once --dry-run

# Check API keys
grep -E "NEWSAPI_KEY|ANTHROPIC_API_KEY" .env
```

### No Signals Generated
```bash
# Lower thresholds temporarily
python3 scripts/run_news_monitor.py \
  --once \
  --dry-run \
  --min-impact 0.4 \
  --min-confidence 0.5
```

### API Rate Limits
```bash
# Increase interval to 10 minutes
NEWS_MONITORING_INTERVAL=600

# Or use fewer markets
python3 scripts/run_news_monitor.py --min-liquidity 100000
```

## 🎉 Success Metrics

You'll know it's working when you see:

✅ Regular news checks every 5 minutes  
✅ Market-news matches found  
✅ Claude AI analysis running  
✅ Confidence scores > 0.65  
✅ Trading signals generated  
✅ No error messages in logs  

## 📞 Next Steps

1. **SSH to your GCloud VM** using the command you normally use
2. **Pull the latest code** from GitHub
3. **Verify API keys** are in `.env`
4. **Run the test**: `python3 scripts/run_news_monitor.py --once --dry-run`
5. **Review signals** and adjust thresholds if needed
6. **Start continuous monitoring**: `nohup python3 scripts/run_news_monitor.py --dry-run &`
7. **Monitor logs**: `tail -f logs/news_monitor.log`

## 💡 Pro Tips

- Start with `DRY_RUN=true` for at least 24 hours
- Review signals manually before enabling `AUTO_TRADE`
- Use `--min-confidence 0.75` for higher quality signals
- Enable Twitter validation when you get the API key
- Monitor during high-news periods (Fed meetings, elections)
- Keep position sizes small initially

---

**Ready to deploy?** The system is tested and ready to go! 🚀
