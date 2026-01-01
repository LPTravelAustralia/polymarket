'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Header } from '@/components/Header'
import { StatsRow } from '@/components/StatsRow'
import { MarketList } from '@/components/MarketList'
import { Sidebar } from '@/components/Sidebar'
import { MarketModal } from '@/components/MarketModal'
import { SettingsPanel } from '@/components/SettingsPanel'
import { api, Market, BotStatus, Portfolio, BotConfig } from '@/lib/api'

const DEFAULT_SETTINGS: BotConfig = {
  trade_size: 25,
  max_markets: 5,
  per_market_cap: 100,
  global_cap: 500,
  drawdown_limit: 200,
  poll_interval: 20,
  take_profit: 0.05,
  stop_loss: 0.03,
  agent: 'momentum',
}

// WebSocket URL - connect directly to backend for real-time updates
// Note: Uses ws:// since backend doesn't have SSL. Browser may block on HTTPS sites.
const getWsUrl = () => {
  if (typeof window === 'undefined') return 'ws://localhost:8000/ws'
  if (process.env.NEXT_PUBLIC_WS_URL) return process.env.NEXT_PUBLIC_WS_URL
  if (window.location.hostname === 'localhost') return 'ws://localhost:8000/ws'
  // Production: connect directly to backend
  return 'ws://136.114.57.247:8000/ws'
}

export default function Home() {
  const queryClient = useQueryClient()
  const [selectedMarket, setSelectedMarket] = useState<Market | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [category, setCategory] = useState('all')
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [botSettings, setBotSettings] = useState<BotConfig>(DEFAULT_SETTINGS)
  const [wsConnected, setWsConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeout = useRef<NodeJS.Timeout | null>(null)

  // WebSocket connection for real-time updates
  const connectWebSocket = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    try {
      const wsUrl = getWsUrl()
      console.log('🔌 Connecting to WebSocket:', wsUrl)
      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.onopen = () => {
        console.log('🔌 WebSocket connected')
        setWsConnected(true)
      }

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          
          if (data.type === 'portfolio') {
            // Update portfolio with real-time data
            queryClient.setQueryData(['portfolio'], (old: Portfolio | undefined) => ({
              ...old,
              positions: data.positions || [],
              total_pnl: data.pnl ?? old?.total_pnl ?? 0,
            }))
            // Also update status
            queryClient.setQueryData(['status'], (old: BotStatus | undefined) => ({
              ...old,
              running: data.running,
            }))
          } else if (data.type === 'trade') {
            // New trade opened - refresh portfolio
            queryClient.invalidateQueries({ queryKey: ['portfolio'] })
            queryClient.invalidateQueries({ queryKey: ['activity'] })
          } else if (data.type === 'close') {
            // Position closed (TP/SL/resolved) - refresh all
            queryClient.invalidateQueries({ queryKey: ['portfolio'] })
            queryClient.invalidateQueries({ queryKey: ['activity'] })
          } else if (data.type === 'activity') {
            // Activity update
            queryClient.invalidateQueries({ queryKey: ['activity'] })
          }
        } catch (e) {
          console.warn('WebSocket message parse error:', e)
        }
      }

      ws.onclose = () => {
        console.log('🔌 WebSocket disconnected')
        setWsConnected(false)
        // Reconnect after 3 seconds
        reconnectTimeout.current = setTimeout(connectWebSocket, 3000)
      }

      ws.onerror = (error) => {
        console.warn('WebSocket error:', error)
        ws.close()
      }
    } catch (e) {
      console.warn('WebSocket connection failed:', e)
      reconnectTimeout.current = setTimeout(connectWebSocket, 3000)
    }
  }, [queryClient])

  // Connect WebSocket on mount
  useEffect(() => {
    connectWebSocket()

    // Send ping every 25 seconds to keep connection alive
    const pingInterval = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: 'ping' }))
      }
    }, 25000)

    return () => {
      clearInterval(pingInterval)
      if (reconnectTimeout.current) clearTimeout(reconnectTimeout.current)
      wsRef.current?.close()
    }
  }, [connectWebSocket])

  // Fetch markets
  const { data: markets, isLoading: marketsLoading } = useQuery({
    queryKey: ['markets', searchQuery, category],
    queryFn: () => api.getMarkets({ search: searchQuery, category, limit: 30 }),
  })

  // Fetch bot status - with WebSocket, we can poll less frequently
  const { data: status } = useQuery({
    queryKey: ['status'],
    queryFn: api.getStatus,
    refetchInterval: wsConnected ? 30000 : 5000,
  })

  // Fetch portfolio - with WebSocket, we can poll less frequently
  const { data: portfolio } = useQuery({
    queryKey: ['portfolio'],
    queryFn: api.getPortfolio,
    refetchInterval: wsConnected ? 30000 : 5000,
  })

  // Fetch equity history for chart
  const { data: equityData } = useQuery({
    queryKey: ['equity-history'],
    queryFn: api.getEquityHistory,
    refetchInterval: 5000,
  })

  // Fetch activity
  const { data: activityData } = useQuery({
    queryKey: ['activity'],
    queryFn: api.getActivity,
    refetchInterval: 5000,
  })

  // Bot controls
  const startBot = useMutation({
    mutationFn: (config?: BotConfig) => api.startBot(config),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['status'] })
      queryClient.invalidateQueries({ queryKey: ['portfolio'] })
    },
  })

  const stopBot = useMutation({
    mutationFn: api.stopBot,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['status'] })
      queryClient.invalidateQueries({ queryKey: ['portfolio'] })
    },
  })

  // Analyze market
  const analyzeMutation = useMutation({
    mutationFn: (marketId: string) => api.analyzeMarket(marketId),
  })

  const handleAnalyze = async (market: Market) => {
    setSelectedMarket(market)
    await analyzeMutation.mutateAsync(market.id)
  }

  return (
    <div className="min-h-screen">
      <div className="max-w-7xl mx-auto px-4 py-6">
        <Header 
          isRunning={status?.running ?? false}
          wsConnected={wsConnected}
        />

        <StatsRow 
          markets={markets ?? []}
          status={status}
        />

        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          <div className="lg:col-span-3">
            <MarketList
              markets={markets ?? []}
              isLoading={marketsLoading}
              searchQuery={searchQuery}
              onSearchChange={setSearchQuery}
              category={category}
              onCategoryChange={setCategory}
              onMarketClick={handleAnalyze}
            />
          </div>

          <div className="lg:col-span-1">
            <Sidebar
              status={status}
              portfolio={portfolio}
              equityHistory={equityData?.history ?? []}
              activities={activityData?.activities ?? []}
              onStart={() => startBot.mutate(botSettings)}
              onStop={() => stopBot.mutate()}
              isStarting={startBot.isPending}
              isStopping={stopBot.isPending}
              onOpenSettings={() => setSettingsOpen(true)}
            />
          </div>
        </div>
      </div>

      {selectedMarket && (
        <MarketModal
          market={selectedMarket}
          analysis={analyzeMutation.data}
          isAnalyzing={analyzeMutation.isPending}
          onClose={() => {
            setSelectedMarket(null)
            analyzeMutation.reset()
          }}
        />
      )}

      <SettingsPanel
        isOpen={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        settings={botSettings}
        onSave={setBotSettings}
        disabled={status?.running}
      />
    </div>
  )
}
