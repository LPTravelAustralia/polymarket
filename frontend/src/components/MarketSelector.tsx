'use client'

import { useState, useEffect } from 'react'
import { X, Search, Check, TrendingUp, DollarSign, Loader2 } from 'lucide-react'

interface SelectableMarket {
  id: string
  question: string
  volume: number
  liquidity: number
  yes_price: number
  volume_24h?: number
}

interface MarketSelectorProps {
  isOpen: boolean
  onClose: () => void
  selectedMarkets: string[]
  onSelectionChange: (markets: string[]) => void
  disabled?: boolean
}

const CATEGORIES = [
  { id: 'all', label: 'All', emoji: '📊' },
  { id: 'politics', label: 'Politics', emoji: '🏛️' },
  { id: 'sports', label: 'Sports', emoji: '⚽' },
  { id: 'crypto', label: 'Crypto', emoji: '₿' },
  { id: 'finance', label: 'Finance', emoji: '📈' },
  { id: 'entertainment', label: 'Entertainment', emoji: '🎬' },
  { id: 'tech', label: 'Tech', emoji: '💻' },
  { id: 'ai', label: 'AI', emoji: '🤖' },
]

export function MarketSelector({ 
  isOpen, 
  onClose, 
  selectedMarkets, 
  onSelectionChange,
  disabled 
}: MarketSelectorProps) {
  const [markets, setMarkets] = useState<SelectableMarket[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState('all')
  const [localSelection, setLocalSelection] = useState<Set<string>>(new Set(selectedMarkets))

  // Fetch markets when modal opens or filters change
  useEffect(() => {
    if (!isOpen) return

    const fetchMarkets = async () => {
      setLoading(true)
      setError(null)
      try {
        const params = new URLSearchParams()
        params.set('limit', '50')
        if (category !== 'all') params.set('category', category)
        if (search) params.set('search', search)
        
        const res = await fetch(`/api/selectable-markets?${params}`)
        if (!res.ok) throw new Error('Failed to fetch markets')
        const data = await res.json()
        setMarkets(data.markets || [])
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load markets')
        setMarkets([])
      } finally {
        setLoading(false)
      }
    }

    const debounce = setTimeout(fetchMarkets, 300)
    return () => clearTimeout(debounce)
  }, [isOpen, search, category])

  // Sync local selection with props
  useEffect(() => {
    setLocalSelection(new Set(selectedMarkets))
  }, [selectedMarkets])

  if (!isOpen) return null

  const toggleMarket = (marketId: string) => {
    const newSelection = new Set(localSelection)
    if (newSelection.has(marketId)) {
      newSelection.delete(marketId)
    } else {
      newSelection.add(marketId)
    }
    setLocalSelection(newSelection)
  }

  const handleSave = () => {
    onSelectionChange(Array.from(localSelection))
    onClose()
  }

  const handleClear = () => {
    setLocalSelection(new Set())
  }

  const formatCurrency = (value: number): string => {
    if (value >= 1000000) return `$${(value / 1000000).toFixed(1)}M`
    if (value >= 1000) return `$${(value / 1000).toFixed(0)}K`
    return `$${Math.round(value)}`
  }

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-gray-900 rounded-2xl border border-white/10 w-full max-w-2xl max-h-[85vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-white/10">
          <div>
            <h2 className="text-xl font-semibold flex items-center gap-2">
              🎯 Select Markets to Trade
            </h2>
            <p className="text-sm text-gray-400 mt-1">
              Choose specific markets or leave empty for auto-discovery
            </p>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-white/10 rounded-lg transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Search & Filters */}
        <div className="p-4 border-b border-white/10 space-y-3">
          {/* Search */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search markets..."
              className="w-full pl-10 pr-4 py-2.5 bg-black/40 border border-white/10 rounded-xl text-sm focus:outline-none focus:border-primary-500"
            />
          </div>
          
          {/* Category Pills */}
          <div className="flex gap-2 flex-wrap">
            {CATEGORIES.map(cat => (
              <button
                key={cat.id}
                onClick={() => setCategory(cat.id)}
                className={`px-3 py-1.5 rounded-full text-xs font-medium transition-all ${
                  category === cat.id
                    ? 'bg-primary-500 text-white'
                    : 'bg-white/5 text-gray-400 hover:bg-white/10'
                }`}
              >
                {cat.emoji} {cat.label}
              </button>
            ))}
          </div>

          {/* Selection Summary */}
          <div className="flex items-center justify-between text-sm">
            <span className="text-gray-400">
              {localSelection.size === 0 
                ? 'No markets selected (bot will auto-discover)' 
                : `${localSelection.size} market${localSelection.size > 1 ? 's' : ''} selected`}
            </span>
            {localSelection.size > 0 && (
              <button 
                onClick={handleClear}
                className="text-red-400 hover:text-red-300 text-xs"
              >
                Clear all
              </button>
            )}
          </div>
        </div>

        {/* Market List */}
        <div className="flex-1 overflow-y-auto p-4 space-y-2">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-8 h-8 animate-spin text-primary-500" />
            </div>
          ) : error ? (
            <div className="text-center py-12 text-red-400">
              <p>{error}</p>
              <button 
                onClick={() => setSearch('')}
                className="mt-2 text-sm text-primary-400 hover:underline"
              >
                Try again
              </button>
            </div>
          ) : markets.length === 0 ? (
            <div className="text-center py-12 text-gray-500">
              <p>No markets found</p>
              <p className="text-sm mt-1">Try a different search or category</p>
            </div>
          ) : (
            markets.map(market => {
              const isSelected = localSelection.has(market.id)
              return (
                <button
                  key={market.id}
                  onClick={() => toggleMarket(market.id)}
                  disabled={disabled}
                  className={`w-full p-4 rounded-xl border text-left transition-all ${
                    isSelected
                      ? 'border-primary-500 bg-primary-500/20'
                      : 'border-white/10 bg-black/20 hover:border-white/20 hover:bg-black/30'
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <p className={`font-medium leading-tight ${isSelected ? 'text-white' : 'text-gray-200'}`}>
                        {market.question}
                      </p>
                      <div className="flex items-center gap-4 mt-2 text-xs text-gray-500">
                        <span className="flex items-center gap-1">
                          <TrendingUp className="w-3 h-3" />
                          {formatCurrency(market.volume_24h || 0)} 24h
                        </span>
                        <span className="flex items-center gap-1">
                          <DollarSign className="w-3 h-3" />
                          {formatCurrency(market.liquidity)} liq
                        </span>
                        <span className={`font-mono ${market.yes_price > 0.5 ? 'text-green-400' : 'text-red-400'}`}>
                          {Math.round(market.yes_price * 100)}%
                        </span>
                      </div>
                    </div>
                    <div className={`w-6 h-6 rounded-full border-2 flex items-center justify-center flex-shrink-0 ${
                      isSelected 
                        ? 'border-primary-500 bg-primary-500' 
                        : 'border-white/30'
                    }`}>
                      {isSelected && <Check className="w-4 h-4 text-white" />}
                    </div>
                  </div>
                </button>
              )
            })
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-white/10 flex justify-between">
          <button
            onClick={onClose}
            className="px-4 py-2 text-gray-400 hover:text-white transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={disabled}
            className="px-6 py-2 bg-primary-500 hover:bg-primary-600 text-white rounded-xl font-medium transition-colors disabled:opacity-50"
          >
            Save Selection
          </button>
        </div>
      </div>
    </div>
  )
}
