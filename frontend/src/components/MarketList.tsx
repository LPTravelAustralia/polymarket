'use client'

import { useState } from 'react'
import { Market, formatCurrency, formatPercent } from '@/lib/api'
import { Search, RefreshCw, TrendingUp, DollarSign, Calendar, Activity, BarChart3, Loader2 } from 'lucide-react'

interface MarketListProps {
  markets: Market[]
  isLoading: boolean
  searchQuery: string
  onSearchChange: (query: string) => void
  category: string
  onCategoryChange: (category: string) => void
  onMarketClick: (market: Market) => void
  sortBy?: string
  onSortChange?: (sort: string) => void
  onQuickTrade?: (marketId: string, side: 'yes' | 'no') => Promise<void>
  existingPositions?: Set<string>
}

const categories = [
  { id: 'all', label: 'All' },
  { id: 'politics', label: 'Politics' },
  { id: 'crypto', label: 'Crypto' },
  { id: 'sports', label: 'Sports' },
  { id: 'finance', label: 'Finance' },
]

const sortOptions = [
  { id: 'volume', label: 'Volume' },
  { id: 'liquidity', label: 'Liquidity' },
  { id: 'end_date', label: 'End Date' },
]

export function MarketList({
  markets,
  isLoading,
  searchQuery,
  onSearchChange,
  category,
  onCategoryChange,
  onMarketClick,
  sortBy = 'volume',
  onSortChange,
  onQuickTrade,
  existingPositions,
}: MarketListProps) {
  const [tradingMarkets, setTradingMarkets] = useState<Set<string>>(new Set())

  const handleQuickTrade = async (e: React.MouseEvent, marketId: string, side: 'yes' | 'no') => {
    e.stopPropagation()
    if (!onQuickTrade) return
    
    setTradingMarkets(prev => new Set(prev).add(marketId))
    try {
      await onQuickTrade(marketId, side)
    } finally {
      setTradingMarkets(prev => {
        const next = new Set(prev)
        next.delete(marketId)
        return next
      })
    }
  }

  return (
    <div className="bg-white/5 rounded-2xl p-6 border border-white/10">
      <h2 className="text-xl font-semibold mb-6 flex items-center gap-2">
        <span className="text-2xl">📊</span> Live Markets
      </h2>

      {/* Search */}
      <div className="flex gap-3 mb-4">
        <div className="flex-1 relative">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Search markets (Trump, Bitcoin, Fed...)"
            className="w-full pl-12 pr-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-500 focus:outline-none focus:border-primary-500 transition-colors"
          />
        </div>
        <button 
          onClick={() => onSearchChange(searchQuery)}
          className="px-6 py-3 bg-primary-500 text-black font-semibold rounded-xl hover:bg-primary-400 transition-colors flex items-center gap-2"
        >
          <RefreshCw className="w-4 h-4" />
          Refresh
        </button>
      </div>

      {/* Category & Sort Filters */}
      <div className="flex gap-4 mb-6 flex-wrap items-center">
        <div className="flex gap-2 flex-wrap">
          {categories.map((cat) => (
            <button
              key={cat.id}
              onClick={() => onCategoryChange(cat.id)}
              className={`px-4 py-2 rounded-full text-sm font-medium transition-colors ${
                category === cat.id
                  ? 'bg-primary-500 text-black'
                  : 'bg-white/10 text-gray-300 hover:bg-white/20'
              }`}
            >
              {cat.label}
            </button>
          ))}
        </div>
        
        {onSortChange && (
          <div className="flex items-center gap-2 ml-auto">
            <span className="text-sm text-gray-400">Sort:</span>
            <select
              value={sortBy}
              onChange={(e) => onSortChange(e.target.value)}
              className="bg-white/10 border border-white/20 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:border-primary-500"
            >
              {sortOptions.map((opt) => (
                <option key={opt.id} value={opt.id} className="bg-gray-900">
                  {opt.label}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      {/* Market List */}
      <div className="space-y-3 max-h-[600px] overflow-y-auto pr-2">
        {isLoading ? (
          // Skeleton loading
          Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="bg-white/5 rounded-xl p-5 animate-pulse">
              <div className="h-5 bg-white/10 rounded w-3/4 mb-4" />
              <div className="h-4 bg-white/10 rounded w-1/2 mb-3" />
              <div className="h-2 bg-white/10 rounded w-full" />
            </div>
          ))
        ) : markets.length === 0 ? (
          <div className="text-center py-12 text-gray-400">
            <span className="text-4xl mb-4 block">🔍</span>
            No markets found
          </div>
        ) : (
          markets.map((market, index) => (
            <MarketCard
              key={market.id}
              market={market}
              index={index}
              onClick={() => onMarketClick(market)}
              onQuickTrade={onQuickTrade ? (side) => handleQuickTrade({ stopPropagation: () => {} } as React.MouseEvent, market.id, side) : undefined}
              isTrading={tradingMarkets.has(market.id)}
              hasPosition={existingPositions?.has(market.id)}
            />
          ))
        )}
      </div>
    </div>
  )
}

function MarketCard({ 
  market, 
  index, 
  onClick,
  onQuickTrade,
  isTrading,
  hasPosition
}: { 
  market: Market
  index: number
  onClick: () => void
  onQuickTrade?: (side: 'yes' | 'no') => void
  isTrading?: boolean
  hasPosition?: boolean
}) {
  const yesPercent = Math.round(market.yes_price * 100)
  const hasVolume24h = market.volume_24h && market.volume_24h > 0

  return (
    <div
      onClick={onClick}
      className="bg-white/5 rounded-xl p-5 cursor-pointer border border-transparent hover:border-primary-500/50 hover:bg-white/10 transition-all animate-fade-in group"
      style={{ animationDelay: `${index * 50}ms` }}
    >
      <div className="flex justify-between items-start gap-4 mb-3">
        <h3 className="font-medium text-white group-hover:text-primary-400 transition-colors line-clamp-2">
          {market.question}
        </h3>
        <span className="shrink-0 px-3 py-1 bg-primary-500/20 text-primary-400 rounded-full text-sm font-semibold">
          {yesPercent}% Yes
        </span>
      </div>

      <div className="flex gap-4 text-sm text-gray-400 mb-3 flex-wrap">
        <span className="flex items-center gap-1.5">
          <DollarSign className="w-4 h-4" />
          {formatCurrency(market.liquidity)}
        </span>
        <span className="flex items-center gap-1.5">
          <TrendingUp className="w-4 h-4" />
          {formatCurrency(market.volume)}
        </span>
        {hasVolume24h && (
          <span className="flex items-center gap-1.5 text-primary-400">
            <BarChart3 className="w-4 h-4" />
            {formatCurrency(market.volume_24h!)} 24h
          </span>
        )}
        {market.end_date && (
          <span className="flex items-center gap-1.5">
            <Calendar className="w-4 h-4" />
            {new Date(market.end_date).toLocaleDateString('en-US', { 
              month: 'short', 
              day: 'numeric' 
            })}
          </span>
        )}
      </div>

      {/* Probability bar */}
      <div className="h-2 bg-red-500/30 rounded-full overflow-hidden mb-3">
        <div
          className="h-full bg-gradient-to-r from-primary-500 to-primary-400 transition-all duration-500"
          style={{ width: `${yesPercent}%` }}
        />
      </div>

      {/* Quick Trade Buttons */}
      {onQuickTrade && (
        <div className="flex gap-2 mt-2 opacity-0 group-hover:opacity-100 transition-opacity">
          {hasPosition ? (
            <span className="flex-1 text-center py-2 bg-white/5 rounded-lg text-xs text-gray-500">
              Already have position
            </span>
          ) : isTrading ? (
            <span className="flex-1 flex items-center justify-center py-2 bg-white/10 rounded-lg text-xs text-gray-400">
              <Loader2 className="w-3 h-3 animate-spin mr-2" />
              Opening...
            </span>
          ) : (
            <>
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  onQuickTrade('yes')
                }}
                className="flex-1 py-2 bg-green-500/20 hover:bg-green-500/40 text-green-400 text-xs font-semibold rounded-lg transition-colors"
              >
                Buy YES
              </button>
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  onQuickTrade('no')
                }}
                className="flex-1 py-2 bg-red-500/20 hover:bg-red-500/40 text-red-400 text-xs font-semibold rounded-lg transition-colors"
              >
                Buy NO
              </button>
            </>
          )}
        </div>
      )}
    </div>
  )
}
