'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Header } from '@/components/Header'
import { StatsRow } from '@/components/StatsRow'
import { MarketList } from '@/components/MarketList'
import { EventList } from '@/components/EventList'
import { Sidebar } from '@/components/Sidebar'
import { SummaryMetrics } from '@/components/SummaryMetrics'
import { MarketModal } from '@/components/MarketModal'
import { SettingsPanel } from '@/components/SettingsPanel'
import { ToastContainer, useToasts } from '@/components/Toast'
import { api, Market, BotStatus, Portfolio, BotConfig, MarketsResponse, EventsResponse } from '@/lib/api'

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
  // New settings with defaults
  categories: [],
  min_liquidity: 1000,
  min_volume: 0,
  min_volume_24h: 0,
  max_spread: 0.1,
  min_volatility: 0,
  use_kelly_sizing: false,
  kelly_fraction: 0.5,
  min_edge: 0.05,
  use_price_momentum: false,
  momentum_period: 24,
  use_volume_filter: false,
  volume_spike_threshold: 2.0,
  auto_exit_on_resolution: true,
  time_to_expiry_filter: 24,
}

// WebSocket only works when:
// - Running locally (localhost)
// - Or backend has SSL (wss://)
// HTTPS pages cannot connect to ws:// (mixed content blocked by browser)
const canUseWebSocket = () => {
  if (typeof window === 'undefined') return false
  // Allow on localhost
  if (window.location.hostname === 'localhost') return true
  // Allow if page is HTTP (not HTTPS)
  if (window.location.protocol === 'http:') return true
  // Allow if we have a secure WebSocket URL configured
  if (process.env.NEXT_PUBLIC_WS_URL?.startsWith('wss://')) return true
  // Otherwise, HTTPS + ws:// = blocked by browser
  return false
}

const getWsUrl = () => {
  if (process.env.NEXT_PUBLIC_WS_URL) return process.env.NEXT_PUBLIC_WS_URL
  if (typeof window !== 'undefined' && window.location.hostname === 'localhost') {
    return 'ws://localhost:8000/ws'
  }
  return 'wss://bot.travorro.com/ws'
}

export default function Home() {
  const queryClient = useQueryClient()
  const [selectedMarket, setSelectedMarket] = useState<Market | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [category, setCategory] = useState('all')
  const [sortBy, setSortBy] = useState('volume')
  const [viewMode, setViewMode] = useState<'markets' | 'events'>('markets')
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [botSettings, setBotSettings] = useState<BotConfig>(DEFAULT_SETTINGS)
  const [wsConnected, setWsConnected] = useState(false)
  const [wsDisabled, setWsDisabled] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeout = useRef<NodeJS.Timeout | null>(null)
  
  // Toast notifications
  const { toasts, dismissToast, showTradeNotification, showCloseNotification, showSuccess, showError } = useToasts()

  // WebSocket connection for real-time updates
  const connectWebSocket = useCallback(() => {
    // Skip if WebSocket not supported in this context
    if (!canUseWebSocket()) {
      setWsDisabled(true)
      return
    }
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
            // New trade opened - show notification and refresh
            if (data.trade) {
              showTradeNotification(
                data.trade.side,
                data.trade.question,
                data.trade.size
              )
            }
            queryClient.invalidateQueries({ queryKey: ['portfolio'] })
            queryClient.invalidateQueries({ queryKey: ['activity'] })
          } else if (data.type === 'close') {
            // Position closed (TP/SL/resolved) - show notification and refresh
            if (data.trade) {
              showCloseNotification(
                data.reason || 'closed',
                data.trade.question,
                data.trade.pnl
              )
            }
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
  const { data: marketsData, isLoading: marketsLoading } = useQuery({
    queryKey: ['markets', searchQuery, category, sortBy],
    queryFn: () => api.getMarkets({ search: searchQuery, category, limit: 50, sortBy }),
    enabled: viewMode === 'markets',
  })

  // Fetch events
  const { data: eventsData, isLoading: eventsLoading } = useQuery({
    queryKey: ['events', searchQuery, sortBy],
    queryFn: () => api.getEvents({ search: searchQuery, limit: 20, sortBy }),
    enabled: viewMode === 'events',
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

  // Fetch 24h summary
  const { data: summary24h } = useQuery({
    queryKey: ['summary24h'],
    queryFn: api.getSummary24h,
    refetchInterval: 10000,
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

  // Close position
  const closePosition = useMutation({
    mutationFn: (marketId: string) => api.closePosition(marketId, 'manual'),
    onSuccess: (data) => {
      showCloseNotification('MANUAL', data.trade.question, data.trade.pnl)
      queryClient.invalidateQueries({ queryKey: ['portfolio'] })
      queryClient.invalidateQueries({ queryKey: ['activity'] })
    },
    onError: (error) => {
      showError('Close Failed', `Failed to close position: ${error.message}`)
    },
  })

  // Quick trade
  const quickTrade = useMutation({
    mutationFn: ({ marketId, side, size }: { marketId: string; side: 'yes' | 'no'; size: number }) => 
      api.quickTrade(marketId, side, size),
    onSuccess: (data) => {
      showTradeNotification(data.trade.side, data.trade.question, data.trade.size)
      queryClient.invalidateQueries({ queryKey: ['portfolio'] })
      queryClient.invalidateQueries({ queryKey: ['activity'] })
    },
    onError: (error) => {
      showError('Trade Failed', `Failed to open trade: ${error.message}`)
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
          wsDisabled={wsDisabled}
        />

        <StatsRow 
          markets={marketsData?.markets ?? []}
          totalMarkets={marketsData?.total ?? 0}
          status={status}
        />

        {/* View Toggle */}
        <div className="flex gap-2 mb-6">
          <button
            onClick={() => setViewMode('markets')}
            className={`px-6 py-2.5 rounded-xl font-medium transition-colors ${
              viewMode === 'markets'
                ? 'bg-primary-500 text-black'
                : 'bg-white/10 text-gray-300 hover:bg-white/20'
            }`}
          >
            📊 Markets
          </button>
          <button
            onClick={() => setViewMode('events')}
            className={`px-6 py-2.5 rounded-xl font-medium transition-colors ${
              viewMode === 'events'
                ? 'bg-primary-500 text-black'
                : 'bg-white/10 text-gray-300 hover:bg-white/20'
            }`}
          >
            🎯 Events
          </button>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          <div className="lg:col-span-3">
            {viewMode === 'markets' ? (
              <MarketList
                markets={marketsData?.markets ?? []}
                isLoading={marketsLoading}
                searchQuery={searchQuery}
                onSearchChange={setSearchQuery}
                category={category}
                onCategoryChange={setCategory}
                onMarketClick={handleAnalyze}
                sortBy={sortBy}
                onSortChange={setSortBy}
                onQuickTrade={async (marketId, side, size) => {
                  await quickTrade.mutateAsync({ marketId, side, size })
                }}
                existingPositions={new Set(portfolio?.positions?.map(p => p.market_id) ?? [])}
                defaultTradeSize={botSettings.trade_size}
              />
            ) : (
              <EventList
                events={eventsData?.events ?? []}
                isLoading={eventsLoading}
                searchQuery={searchQuery}
                onSearchChange={setSearchQuery}
                onMarketClick={handleAnalyze}
                sortBy={sortBy}
                onSortChange={setSortBy}
              />
            )}
          </div>

          <div className="lg:col-span-1 space-y-6">
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
              onClosePosition={async (marketId) => {
                await closePosition.mutateAsync(marketId)
              }}
            />
            <SummaryMetrics summary={summary24h} />
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
          onAnalyze={() => {
            analyzeMutation.mutate(selectedMarket.id)
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

      {/* Toast Notifications */}
      <ToastContainer toasts={toasts} onDismiss={dismissToast} />
    </div>
  )
}
