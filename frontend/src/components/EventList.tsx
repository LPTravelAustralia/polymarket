'use client'

import { Event, Market, formatCurrency } from '@/lib/api'
import { Search, RefreshCw, TrendingUp, DollarSign, Calendar, ChevronDown, ChevronRight } from 'lucide-react'
import { useState } from 'react'

interface EventListProps {
  events: Event[]
  isLoading: boolean
  searchQuery: string
  onSearchChange: (query: string) => void
  onMarketClick: (market: Market) => void
  sortBy?: string
  onSortChange?: (sort: string) => void
}

const sortOptions = [
  { id: 'volume', label: 'Volume' },
  { id: 'liquidity', label: 'Liquidity' },
  { id: 'end_date', label: 'End Date' },
]

export function EventList({
  events,
  isLoading,
  searchQuery,
  onSearchChange,
  onMarketClick,
  sortBy = 'volume',
  onSortChange,
}: EventListProps) {
  return (
    <div className="bg-white/5 rounded-2xl p-6 border border-white/10">
      <h2 className="text-xl font-semibold mb-6 flex items-center gap-2">
        <span className="text-2xl">🎯</span> Events
      </h2>

      {/* Search */}
      <div className="flex gap-3 mb-4">
        <div className="flex-1 relative">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Search events..."
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

      {/* Sort */}
      {onSortChange && (
        <div className="flex items-center gap-2 mb-6">
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

      {/* Event List */}
      <div className="space-y-4 max-h-[600px] overflow-y-auto pr-2">
        {isLoading ? (
          // Skeleton loading
          Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="bg-white/5 rounded-xl p-5 animate-pulse">
              <div className="h-6 bg-white/10 rounded w-3/4 mb-4" />
              <div className="h-4 bg-white/10 rounded w-1/2 mb-3" />
              <div className="space-y-2">
                <div className="h-3 bg-white/10 rounded w-full" />
                <div className="h-3 bg-white/10 rounded w-full" />
              </div>
            </div>
          ))
        ) : events.length === 0 ? (
          <div className="text-center py-12 text-gray-400">
            <span className="text-4xl mb-4 block">🔍</span>
            No events found
          </div>
        ) : (
          events.map((event, index) => (
            <EventCard
              key={event.id}
              event={event}
              index={index}
              onMarketClick={onMarketClick}
            />
          ))
        )}
      </div>
    </div>
  )
}

function EventCard({ 
  event, 
  index, 
  onMarketClick 
}: { 
  event: Event
  index: number
  onMarketClick: (market: Market) => void
}) {
  const [expanded, setExpanded] = useState(false)
  const marketCount = event.markets.length

  return (
    <div
      className="bg-white/5 rounded-xl border border-transparent hover:border-primary-500/30 transition-all animate-fade-in"
      style={{ animationDelay: `${index * 50}ms` }}
    >
      {/* Event Header */}
      <div 
        className="p-5 cursor-pointer"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex justify-between items-start gap-4 mb-3">
          <div className="flex items-start gap-3">
            {expanded ? (
              <ChevronDown className="w-5 h-5 text-gray-400 mt-0.5 shrink-0" />
            ) : (
              <ChevronRight className="w-5 h-5 text-gray-400 mt-0.5 shrink-0" />
            )}
            <div>
              <h3 className="font-medium text-white">
                {event.title}
              </h3>
              {event.description && (
                <p className="text-sm text-gray-400 mt-1 line-clamp-2">
                  {event.description}
                </p>
              )}
            </div>
          </div>
          <span className="shrink-0 px-3 py-1 bg-blue-500/20 text-blue-400 rounded-full text-sm font-medium">
            {marketCount} market{marketCount !== 1 ? 's' : ''}
          </span>
        </div>

        <div className="flex gap-5 text-sm text-gray-400 ml-8">
          <span className="flex items-center gap-1.5">
            <DollarSign className="w-4 h-4" />
            {formatCurrency(event.total_liquidity)}
          </span>
          <span className="flex items-center gap-1.5">
            <TrendingUp className="w-4 h-4" />
            {formatCurrency(event.total_volume)}
          </span>
          {event.end_date && (
            <span className="flex items-center gap-1.5">
              <Calendar className="w-4 h-4" />
              {new Date(event.end_date).toLocaleDateString('en-US', { 
                month: 'short', 
                day: 'numeric',
                year: 'numeric'
              })}
            </span>
          )}
        </div>
      </div>

      {/* Expanded Markets */}
      {expanded && event.markets.length > 0 && (
        <div className="border-t border-white/10 p-4 space-y-2">
          {event.markets.map((market) => (
            <div
              key={market.id}
              onClick={() => onMarketClick(market)}
              className="flex items-center justify-between p-3 bg-white/5 rounded-lg cursor-pointer hover:bg-white/10 transition-colors"
            >
              <span className="text-sm text-white line-clamp-1 flex-1 mr-4">
                {market.question}
              </span>
              <div className="flex items-center gap-4 shrink-0">
                <span className="text-sm text-gray-400">
                  {formatCurrency(market.volume)}
                </span>
                <span className="px-2 py-0.5 bg-primary-500/20 text-primary-400 rounded text-sm font-medium">
                  {Math.round(market.yes_price * 100)}%
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
