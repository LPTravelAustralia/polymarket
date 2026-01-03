// Default to relative API paths in production to avoid mixed-content issues from HTTPS pages calling HTTP APIs.
const API_URL = process.env.NEXT_PUBLIC_API_URL || ''

export interface Market {
  id: string
  question: string
  liquidity: number
  volume: number
  volume_24h?: number
  yes_price: number
  no_price: number
  spread?: number
  end_date?: string
  category?: string
  slug?: string
  closed?: boolean
  resolved_outcome?: string
  event_id?: string
  event_slug?: string
  description?: string
  image?: string
}

export interface Event {
  id: string
  title: string
  slug?: string
  description?: string
  image?: string
  end_date?: string
  markets: Market[]
  total_volume: number
  total_liquidity: number
}

export interface EventsResponse {
  events: Event[]
  total: number
  showing: number
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

export interface TradingStats {
  total_trades: number
  winning_trades: number
  losing_trades: number
  win_rate: number
  avg_win: number
  avg_loss: number
  best_trade: number
  worst_trade: number
  profit_factor: number
}

export interface Portfolio {
  positions: Position[]
  trades: Trade[]
  closed_trades: ClosedTrade[]
  total_pnl: number
  realized_pnl: number
  unrealized_pnl: number
  exposure: number
  stats?: TradingStats
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
  take_profit: number
  stop_loss: number
  // Advanced settings
  categories?: string[]
  min_liquidity?: number
  min_volume?: number
  min_volume_24h?: number
  max_spread?: number
  use_kelly_sizing?: boolean
  kelly_fraction?: number
  min_edge?: number
  use_price_momentum?: boolean
  momentum_period?: number
  use_volume_filter?: boolean
  volume_spike_threshold?: number
  min_volatility?: number
  auto_exit_on_resolution?: boolean
  time_to_expiry_filter?: number
}

export interface MarketsResponse {
  markets: Market[]
  total: number
  showing: number
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
  getMarkets: async (params?: { 
    search?: string
    category?: string
    limit?: number
    offset?: number
    sortBy?: string 
  }): Promise<MarketsResponse> => {
    const searchParams = new URLSearchParams()
    if (params?.search) searchParams.set('search', params.search)
    if (params?.category && params.category !== 'all') searchParams.set('category', params.category)
    if (params?.limit) searchParams.set('limit', params.limit.toString())
    if (params?.offset) searchParams.set('offset', params.offset.toString())
    if (params?.sortBy) searchParams.set('sort_by', params.sortBy)
    
    const query = searchParams.toString()
    return fetchAPI(`/api/markets${query ? `?${query}` : ''}`)
  },

  // Events (grouped markets)
  getEvents: async (params?: {
    search?: string
    limit?: number
    offset?: number
    sortBy?: string
  }): Promise<EventsResponse> => {
    const searchParams = new URLSearchParams()
    if (params?.search) searchParams.set('search', params.search)
    if (params?.limit) searchParams.set('limit', params.limit.toString())
    if (params?.offset) searchParams.set('offset', params.offset.toString())
    if (params?.sortBy) searchParams.set('sort_by', params.sortBy)
    
    const query = searchParams.toString()
    return fetchAPI(`/api/events${query ? `?${query}` : ''}`)
  },

  getEvent: async (id: string): Promise<Event> => {
    return fetchAPI(`/api/events/${id}`)
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
      take_profit: 0.05,
      stop_loss: 0.03,
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

  // Position management
  closePosition: async (marketId: string, reason: string = 'manual'): Promise<{ 
    success: boolean
    message: string
    pnl: number
    trade: ClosedTrade 
  }> => {
    return fetchAPI('/api/bot/close-position', {
      method: 'POST',
      body: JSON.stringify({ market_id: marketId, reason }),
    })
  },

  quickTrade: async (marketId: string, side: 'yes' | 'no', size: number = 10): Promise<{
    success: boolean
    message: string
    trade: Trade
    position: Position
  }> => {
    return fetchAPI('/api/bot/quick-trade', {
      method: 'POST',
      body: JSON.stringify({ market_id: marketId, side, size }),
    })
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
