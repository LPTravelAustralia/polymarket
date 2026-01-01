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
  startBot: async (): Promise<{ success: boolean; message: string }> => {
    return fetchAPI('/api/bot/start', { method: 'POST' })
  },

  stopBot: async (): Promise<{ success: boolean; message: string }> => {
    return fetchAPI('/api/bot/stop', { method: 'POST' })
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
