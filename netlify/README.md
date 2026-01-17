# Polymarket Dashboard - Netlify Deployment

A static dashboard for viewing live Polymarket prediction market data.

## 🚀 Deploy to Netlify

### Option 1: Drag & Drop
1. Go to [app.netlify.com](https://app.netlify.com)
2. Drag the entire `netlify` folder onto the deploy area
3. Done! Your site is live.

### Option 2: GitHub Integration
1. Push this folder to a GitHub repo
2. In Netlify: New Site → Import from Git
3. Select your repo
4. Set publish directory to: `netlify`
5. Deploy!

### Option 3: Netlify CLI
```bash
# Install CLI
npm install -g netlify-cli

# Login
netlify login

# Deploy
cd netlify
netlify deploy --prod
```

## ✨ Features

- **Live Data**: Fetches real-time data from Polymarket's Gamma API
- **Search**: Find markets by keyword
- **Filter**: Filter by Politics, Crypto, Sports, Finance
- **Auto-Refresh**: Updates every 60 seconds
- **Click to Trade**: Opens Polymarket for trading
- **Mobile Friendly**: Responsive design

## ⚠️ Limitations

This is a **view-only** dashboard. For actual trading, you need the full Python bot with API credentials.

## 🔗 Related

- Full trading bot: See main repository
- Polymarket: https://polymarket.com
- Gamma API: https://gamma-api.polymarket.com
