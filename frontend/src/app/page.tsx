'use client'

import { useState, useEffect } from 'react'
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

export default function Home() {
  const queryClient = useQueryClient()
  const [selectedMarket, setSelectedMarket] = useState<Market | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [category, setCategory] = useState('all')
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [botSettings, setBotSettings] = useState<BotConfig>(DEFAULT_SETTINGS)

  // Fetch markets
  const { data: markets, isLoading: marketsLoading } = useQuery({
    queryKey: ['markets', searchQuery, category],
    queryFn: () => api.getMarkets({ search: searchQuery, category, limit: 30 }),
  })

  // Fetch bot status
  const { data: status } = useQuery({
    queryKey: ['status'],
    queryFn: api.getStatus,
    refetchInterval: 5000,
  })

  // Fetch portfolio
  const { data: portfolio } = useQuery({
    queryKey: ['portfolio'],
    queryFn: api.getPortfolio,
    refetchInterval: 5000,
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
