'use client'

import { Market, formatCurrency, formatPercent } from '@/lib/api'
import { Search, RefreshCw, TrendingUp, DollarSign, Calendar } from 'lucide-react'

interface MarketListProps {
  markets: Market[]
  isLoading: boolean
  searchQuery: string
  onSearchChange: (query: string) => void
  category: string
  onCategoryChange: (category: string) => void
  onMarketClick: (market: Market) => void
}

const categories = [
  { id: 'all', label: 'All' },
  { id: 'politics', label: 'Politics' },
  { id: 'crypto', label: 'Crypto' },
  { id: 'sports', label: 'Sports' },
  { id: 'finance', label: 'Finance' },
]

export function MarketList({
  markets,
  isLoading,
  searchQuery,
  onSearchChange,
  category,
  onCategoryChange,
  onMarketClick,
}: MarketListProps) {
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

      {/* Category Filters */}
      <div className="flex gap-2 mb-6 flex-wrap">
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
  onClick 
}: { 
  market: Market
  index: number
  onClick: () => void 
}) {
  const yesPercent = Math.round(market.yes_price * 100)

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

      <div className="flex gap-5 text-sm text-gray-400 mb-3">
        <span className="flex items-center gap-1.5">
          <DollarSign className="w-4 h-4" />
          {formatCurrency(market.liquidity)}
        </span>
        <span className="flex items-center gap-1.5">
          <TrendingUp className="w-4 h-4" />
          {formatCurrency(market.volume)}
        </span>
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
      <div className="h-2 bg-red-500/30 rounded-full overflow-hidden">
        <div
          className="h-full bg-gradient-to-r from-primary-500 to-primary-400 transition-all duration-500"
          style={{ width: `${yesPercent}%` }}
        />
      </div>
    </div>
  )
}
