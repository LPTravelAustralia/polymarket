// Default to relative API paths in production to avoid mixed-content issues from HTTPS pages calling HTTP APIs.
const API_URL = process.env.NEXT_PUBLIC_API_URL || ''

export interface Market {
  id: string
  question: string
  liquidity: number
  volume: number
  yes_price: number
  no_price: number
  end_date?: string
  category?: string
  slug?: string
}

export interface BotStatus {
  running: boolean
  trades_today: number
  total_pnl: number
  win_rate: number
  active_positions: number
  last_update?: string
}

export interface Analysis {
  market_id: string
  question: string
  recommendation: 'BUY_YES' | 'BUY_NO' | 'HOLD'
  confidence: number
  predicted_probability: number
  reasoning: string
  edge: number
}

export interface Position {
  market_id: string
  question: string
  side: string
  size: number
  entry_price: number
  mark_price: number
  unrealized_pnl: number
  last_update: string
}

export interface Trade {
  market_id: string
  question: string
  side: string
  size: number
  entry_price: number
  timestamp: string
  mode: string
}

export interface ClosedTrade {
  market_id: string
  question: string
  side: string
  size: number
  entry_price: number
  exit_price: number
  pnl: number
  reason: string  // 'TP' | 'SL'
  opened_at: string
  closed_at: string
}

export interface Portfolio {
  positions: Position[]
  trades: Trade[]
  closed_trades: ClosedTrade[]
  total_pnl: number
  realized_pnl: number
  unrealized_pnl: number
  exposure: number
}

export interface BotConfig {
  trade_size: number
  max_markets: number
  per_market_cap: number
  global_cap: number
  drawdown_limit: number
  poll_interval: number
  agent: string
  markets?: string[] | null
  take_profit?: number
  stop_loss?: number
}

async function fetchAPI<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${endpoint}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  })
  
  if (!res.ok) {
    throw new Error(`API error: ${res.status}`)
  }
  
  return res.json()
}

export const api = {
  // Markets
  getMarkets: async (params?: { search?: string; category?: string; limit?: number }): Promise<Market[]> => {
    const searchParams = new URLSearchParams()
    if (params?.search) searchParams.set('search', params.search)
    if (params?.category && params.category !== 'all') searchParams.set('category', params.category)
    if (params?.limit) searchParams.set('limit', params.limit.toString())
    
    const query = searchParams.toString()
    return fetchAPI(`/api/markets${query ? `?${query}` : ''}`)
  },

  getMarket: async (id: string): Promise<Market> => {
    return fetchAPI(`/api/markets/${id}`)
  },

  // Bot Status
  getStatus: async (): Promise<BotStatus> => {
    return fetchAPI('/api/status')
  },

  getActivity: async (): Promise<{ activities: string[] }> => {
    return fetchAPI('/api/activity')
  },

  // Bot Controls
  startBot: async (config?: BotConfig): Promise<{ success: boolean; message: string; config?: BotConfig }> => {
    const defaultConfig: BotConfig = {
      trade_size: 25,
      max_markets: 5,
      per_market_cap: 100,
      global_cap: 500,
      drawdown_limit: 200,
      poll_interval: 20,
      agent: 'momentum',
      markets: null,
    }
    return fetchAPI('/api/bot/start', {
      method: 'POST',
      body: JSON.stringify(config ?? defaultConfig),
    })
  },

  stopBot: async (): Promise<{ success: boolean; message: string }> => {
    return fetchAPI('/api/bot/stop', { method: 'POST' })
  },

  getPortfolio: async (): Promise<Portfolio> => {
    return fetchAPI('/api/bot/portfolio')
  },

  getEquityHistory: async (): Promise<{ history: { timestamp: string; pnl: number; positions: number; exposure: number }[] }> => {
    return fetchAPI('/api/bot/equity-history')
  },

  // Analysis
  analyzeMarket: async (marketId: string): Promise<Analysis> => {
    return fetchAPI(`/api/analyze/${marketId}`, { method: 'POST' })
  },

  // Trading
  executeTrade: async (params: { market_id: string; side: 'yes' | 'no'; amount: number }) => {
    return fetchAPI('/api/trade', {
      method: 'POST',
      body: JSON.stringify(params),
    })
  },
}

// Format helpers
export const formatCurrency = (value: number): string => {
  if (value >= 1000000) {
    return `$${(value / 1000000).toFixed(1)}M`
  } else if (value >= 1000) {
    return `$${(value / 1000).toFixed(0)}K`
  }
  return `$${Math.round(value)}`
}

export const formatPercent = (value: number): string => {
  return `${Math.round(value * 100)}%`
}
