# Polymarket Trading Bot - Frontend

Modern Next.js dashboard for the Polymarket trading bot.

## Quick Start

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000

## Environment Variables

Create `.env.local`:
```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

For production:
```
NEXT_PUBLIC_API_URL=https://your-backend-url.railway.app
```

## Features

- 📊 Live market data with auto-refresh
- 🔍 Search and filter markets
- 🤖 AI market analysis
- ▶️ Bot start/stop controls
- 📈 Real-time statistics
- 📋 Activity log
- 📱 Fully responsive

## Deployment

### Vercel (Recommended)
```bash
npm i -g vercel
vercel
```

Or connect your GitHub repo at vercel.com

### Netlify
```bash
npm run build
# Upload the .next folder
```

## Tech Stack

- Next.js 14
- React 18
- TailwindCSS
- React Query
- TypeScript
- Lucide Icons
