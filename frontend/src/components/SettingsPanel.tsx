'use client'

import { useState } from 'react'
import { Settings, X, ChevronDown, ChevronUp, Info } from 'lucide-react'

interface BotSettings {
  trade_size: number
  max_markets: number
  per_market_cap: number
  global_cap: number
  drawdown_limit: number
  poll_interval: number
  take_profit: number
  stop_loss: number
  agent: string
  // New settings (optional with defaults)
  categories?: string[]
  min_liquidity?: number
  min_volume?: number
  max_spread?: number
  use_kelly_sizing?: boolean
  kelly_fraction?: number
  min_edge?: number
  use_price_momentum?: boolean
  momentum_period?: number
  use_volume_filter?: boolean
  volume_spike_threshold?: number
  auto_exit_on_resolution?: boolean
  time_to_expiry_filter?: number // hours
}

// Available market categories
const MARKET_CATEGORIES = [
  { id: 'politics', label: 'Politics', emoji: '🏛️' },
  { id: 'sports', label: 'Sports', emoji: '⚽' },
  { id: 'crypto', label: 'Crypto', emoji: '₿' },
  { id: 'finance', label: 'Finance', emoji: '📈' },
  { id: 'entertainment', label: 'Entertainment', emoji: '🎬' },
  { id: 'tech', label: 'Tech', emoji: '💻' },
  { id: 'science', label: 'Science', emoji: '🔬' },
  { id: 'world', label: 'World News', emoji: '🌍' },
  { id: 'elections', label: 'Elections', emoji: '🗳️' },
  { id: 'ai', label: 'AI', emoji: '🤖' },
]

// Trading strategies with descriptions
const TRADING_STRATEGIES = [
  { 
    id: 'momentum', 
    label: 'Momentum', 
    description: 'Trade based on bid/ask imbalances and price direction',
    icon: '📊'
  },
  { 
    id: 'ai', 
    label: 'AI Superforecaster', 
    description: 'Use GPT-4/Claude with Tetlock methodology for predictions',
    icon: '🧠'
  },
  { 
    id: 'arbitrage', 
    label: 'Arbitrage', 
    description: 'Find mispriced markets where probabilities don\'t sum to 100%',
    icon: '⚖️'
  },
  { 
    id: 'value', 
    label: 'Value Betting', 
    description: 'Find markets where odds differ significantly from true probability',
    icon: '💎'
  },
  { 
    id: 'news', 
    label: 'News Sentiment', 
    description: 'Trade based on real-time news sentiment analysis',
    icon: '📰'
  },
  { 
    id: 'combined', 
    label: 'Multi-Strategy', 
    description: 'Combine multiple strategies with weighted signals',
    icon: '🔀'
  },
]

interface SettingsPanelProps {
  isOpen: boolean
  onClose: () => void
  settings: BotSettings
  onSave: (settings: BotSettings) => void
  disabled?: boolean
}

export function SettingsPanel({ isOpen, onClose, settings, onSave, disabled }: SettingsPanelProps) {
  const [localSettings, setLocalSettings] = useState<BotSettings>(settings)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [activeTab, setActiveTab] = useState<'basic' | 'strategy' | 'filters' | 'risk'>('basic')

  if (!isOpen) return null

  const handleSave = () => {
    onSave(localSettings)
    onClose()
  }

  const updateSetting = <K extends keyof BotSettings>(key: K, value: BotSettings[K]) => {
    setLocalSettings(prev => ({ ...prev, [key]: value }))
  }

  const toggleCategory = (categoryId: string) => {
    const current = localSettings.categories || []
    if (current.includes(categoryId)) {
      updateSetting('categories', current.filter(c => c !== categoryId))
    } else {
      updateSetting('categories', [...current, categoryId])
    }
  }

  const tabs = [
    { id: 'basic', label: 'Basic', icon: '⚙️' },
    { id: 'strategy', label: 'Strategy', icon: '🎯' },
    { id: 'filters', label: 'Filters', icon: '🔍' },
    { id: 'risk', label: 'Risk', icon: '🛡️' },
  ] as const

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-gray-900 rounded-2xl border border-white/10 w-full max-w-lg max-h-[90vh] overflow-hidden flex flex-col">
        <div className="flex items-center justify-between p-6 border-b border-white/10">
          <h2 className="text-xl font-semibold flex items-center gap-2">
            <Settings className="w-5 h-5" />
            Bot Settings
          </h2>
          <button onClick={onClose} className="p-2 hover:bg-white/10 rounded-lg transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Tab Navigation */}
        <div className="flex border-b border-white/10">
          {tabs.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex-1 px-4 py-3 text-sm font-medium transition-colors ${
                activeTab === tab.id 
                  ? 'text-primary-400 border-b-2 border-primary-400 bg-primary-500/10' 
                  : 'text-gray-400 hover:text-white hover:bg-white/5'
              }`}
            >
              <span className="mr-1">{tab.icon}</span>
              {tab.label}
            </button>
          ))}
        </div>

        <div className="p-6 space-y-5 overflow-y-auto flex-1">
          {/* BASIC TAB */}
          {activeTab === 'basic' && (
            <>
              {/* Trade Size */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Trade Size: ${localSettings.trade_size}
                </label>
                <input
                  type="range"
                  min="5"
                  max="100"
                  step="5"
                  value={localSettings.trade_size}
                  onChange={(e) => updateSetting('trade_size', Number(e.target.value))}
                  disabled={disabled}
                  className="w-full accent-primary-500"
                />
                <div className="flex justify-between text-xs text-gray-500 mt-1">
                  <span>$5</span>
                  <span>$100</span>
                </div>
              </div>

              {/* Max Markets */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Max Positions: {localSettings.max_markets}
                </label>
                <input
                  type="range"
                  min="1"
                  max="20"
                  value={localSettings.max_markets}
                  onChange={(e) => updateSetting('max_markets', Number(e.target.value))}
                  disabled={disabled}
                  className="w-full accent-primary-500"
                />
                <div className="flex justify-between text-xs text-gray-500 mt-1">
                  <span>1</span>
                  <span>20</span>
                </div>
              </div>

              {/* Max Exposure */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Max Exposure: ${localSettings.global_cap}
                </label>
                <input
                  type="range"
                  min="100"
                  max="2000"
                  step="100"
                  value={localSettings.global_cap}
                  onChange={(e) => updateSetting('global_cap', Number(e.target.value))}
                  disabled={disabled}
                  className="w-full accent-primary-500"
                />
                <div className="flex justify-between text-xs text-gray-500 mt-1">
                  <span>$100</span>
                  <span>$2000</span>
                </div>
              </div>

              {/* Poll Interval */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Poll Interval: {localSettings.poll_interval}s
                </label>
                <input
                  type="range"
                  min="10"
                  max="120"
                  step="5"
                  value={localSettings.poll_interval}
                  onChange={(e) => updateSetting('poll_interval', Number(e.target.value))}
                  disabled={disabled}
                  className="w-full accent-primary-500"
                />
                <div className="flex justify-between text-xs text-gray-500 mt-1">
                  <span>10s</span>
                  <span>120s</span>
                </div>
              </div>
            </>
          )}

          {/* STRATEGY TAB */}
          {activeTab === 'strategy' && (
            <>
              {/* Strategy Selection */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-3">Trading Strategy</label>
                <div className="space-y-2">
                  {TRADING_STRATEGIES.map(strategy => (
                    <button
                      key={strategy.id}
                      onClick={() => updateSetting('agent', strategy.id)}
                      disabled={disabled}
                      className={`w-full p-3 rounded-xl border text-left transition-all ${
                        localSettings.agent === strategy.id
                          ? 'border-primary-500 bg-primary-500/20 text-white'
                          : 'border-white/10 bg-black/20 text-gray-300 hover:border-white/30'
                      }`}
                    >
                      <div className="flex items-center gap-3">
                        <span className="text-2xl">{strategy.icon}</span>
                        <div>
                          <div className="font-medium">{strategy.label}</div>
                          <div className="text-xs text-gray-400">{strategy.description}</div>
                        </div>
                      </div>
                    </button>
                  ))}
                </div>
              </div>

              {/* Kelly Criterion Toggle */}
              <div className="p-4 rounded-xl bg-black/30 border border-white/10">
                <div className="flex items-center justify-between mb-2">
                  <label className="text-sm font-medium text-gray-300 flex items-center gap-2">
                    📐 Kelly Criterion Sizing
                    <span className="text-xs text-gray-500" title="Optimal bet sizing based on edge">[?]</span>
                  </label>
                  <button
                    onClick={() => updateSetting('use_kelly_sizing', !localSettings.use_kelly_sizing)}
                    disabled={disabled}
                    className={`w-12 h-6 rounded-full transition-colors ${
                      localSettings.use_kelly_sizing ? 'bg-primary-500' : 'bg-gray-600'
                    }`}
                  >
                    <div className={`w-5 h-5 bg-white rounded-full transition-transform ${
                      localSettings.use_kelly_sizing ? 'translate-x-6' : 'translate-x-0.5'
                    }`} />
                  </button>
                </div>
                {localSettings.use_kelly_sizing && (
                  <div className="mt-3">
                    <label className="block text-xs text-gray-400 mb-1">
                      Kelly Fraction: {((localSettings.kelly_fraction || 0.5) * 100).toFixed(0)}% (Half-Kelly recommended)
                    </label>
                    <input
                      type="range"
                      min="0.1"
                      max="1"
                      step="0.1"
                      value={localSettings.kelly_fraction || 0.5}
                      onChange={(e) => updateSetting('kelly_fraction', Number(e.target.value))}
                      disabled={disabled}
                      className="w-full accent-primary-500"
                    />
                  </div>
                )}
              </div>

              {/* Price Momentum Toggle */}
              <div className="p-4 rounded-xl bg-black/30 border border-white/10">
                <div className="flex items-center justify-between mb-2">
                  <label className="text-sm font-medium text-gray-300">📈 Price Momentum Filter</label>
                  <button
                    onClick={() => updateSetting('use_price_momentum', !localSettings.use_price_momentum)}
                    disabled={disabled}
                    className={`w-12 h-6 rounded-full transition-colors ${
                      localSettings.use_price_momentum ? 'bg-primary-500' : 'bg-gray-600'
                    }`}
                  >
                    <div className={`w-5 h-5 bg-white rounded-full transition-transform ${
                      localSettings.use_price_momentum ? 'translate-x-6' : 'translate-x-0.5'
                    }`} />
                  </button>
                </div>
                <p className="text-xs text-gray-500">Only trade in direction of recent price movement</p>
              </div>
            </>
          )}

          {/* FILTERS TAB */}
          {activeTab === 'filters' && (
            <>
              {/* Category Filters */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-3">
                  Market Categories
                  <span className="text-xs text-gray-500 ml-2">
                    ({(localSettings.categories || []).length === 0 ? 'All' : (localSettings.categories || []).length + ' selected'})
                  </span>
                </label>
                <div className="grid grid-cols-2 gap-2">
                  {MARKET_CATEGORIES.map(category => (
                    <button
                      key={category.id}
                      onClick={() => toggleCategory(category.id)}
                      disabled={disabled}
                      className={`p-2 rounded-lg border text-sm transition-all ${
                        (localSettings.categories || []).includes(category.id)
                          ? 'border-primary-500 bg-primary-500/20 text-white'
                          : 'border-white/10 bg-black/20 text-gray-400 hover:border-white/30'
                      }`}
                    >
                      <span className="mr-1">{category.emoji}</span>
                      {category.label}
                    </button>
                  ))}
                </div>
                <p className="text-xs text-gray-500 mt-2">Leave empty to trade all categories</p>
              </div>

              {/* Minimum Liquidity */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Min Liquidity: ${(localSettings.min_liquidity || 1000).toLocaleString()}
                </label>
                <input
                  type="range"
                  min="100"
                  max="50000"
                  step="500"
                  value={localSettings.min_liquidity || 1000}
                  onChange={(e) => updateSetting('min_liquidity', Number(e.target.value))}
                  disabled={disabled}
                  className="w-full accent-primary-500"
                />
                <div className="flex justify-between text-xs text-gray-500 mt-1">
                  <span>$100</span>
                  <span>$50k</span>
                </div>
              </div>

              {/* Minimum Volume */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Min 24h Volume: ${(localSettings.min_volume || 500).toLocaleString()}
                </label>
                <input
                  type="range"
                  min="0"
                  max="10000"
                  step="250"
                  value={localSettings.min_volume || 500}
                  onChange={(e) => updateSetting('min_volume', Number(e.target.value))}
                  disabled={disabled}
                  className="w-full accent-primary-500"
                />
                <div className="flex justify-between text-xs text-gray-500 mt-1">
                  <span>$0</span>
                  <span>$10k</span>
                </div>
              </div>

              {/* Max Spread */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Max Spread: {((localSettings.max_spread || 0.1) * 100).toFixed(0)}%
                </label>
                <input
                  type="range"
                  min="0.01"
                  max="0.2"
                  step="0.01"
                  value={localSettings.max_spread || 0.1}
                  onChange={(e) => updateSetting('max_spread', Number(e.target.value))}
                  disabled={disabled}
                  className="w-full accent-primary-500"
                />
                <div className="flex justify-between text-xs text-gray-500 mt-1">
                  <span>1%</span>
                  <span>20%</span>
                </div>
              </div>

              {/* Time to Expiry */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Min Time to Expiry: {localSettings.time_to_expiry_filter || 24}h
                </label>
                <input
                  type="range"
                  min="1"
                  max="168"
                  step="1"
                  value={localSettings.time_to_expiry_filter || 24}
                  onChange={(e) => updateSetting('time_to_expiry_filter', Number(e.target.value))}
                  disabled={disabled}
                  className="w-full accent-primary-500"
                />
                <div className="flex justify-between text-xs text-gray-500 mt-1">
                  <span>1h</span>
                  <span>7 days</span>
                </div>
              </div>
            </>
          )}

          {/* RISK TAB */}
          {activeTab === 'risk' && (
            <>
              {/* Take Profit */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Take Profit: {(localSettings.take_profit * 100).toFixed(0)}%
                </label>
                <input
                  type="range"
                  min="0.01"
                  max="0.50"
                  step="0.01"
                  value={localSettings.take_profit}
                  onChange={(e) => updateSetting('take_profit', Number(e.target.value))}
                  disabled={disabled}
                  className="w-full accent-green-500"
                />
                <div className="flex justify-between text-xs text-gray-500 mt-1">
                  <span>1%</span>
                  <span>50%</span>
                </div>
              </div>

              {/* Stop Loss */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Stop Loss: {(localSettings.stop_loss * 100).toFixed(0)}%
                </label>
                <input
                  type="range"
                  min="0.01"
                  max="0.30"
                  step="0.01"
                  value={localSettings.stop_loss}
                  onChange={(e) => updateSetting('stop_loss', Number(e.target.value))}
                  disabled={disabled}
                  className="w-full accent-red-500"
                />
                <div className="flex justify-between text-xs text-gray-500 mt-1">
                  <span>1%</span>
                  <span>30%</span>
                </div>
              </div>

              {/* Drawdown Limit */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Daily Drawdown Limit: ${localSettings.drawdown_limit}
                </label>
                <input
                  type="range"
                  min="50"
                  max="500"
                  step="25"
                  value={localSettings.drawdown_limit}
                  onChange={(e) => updateSetting('drawdown_limit', Number(e.target.value))}
                  disabled={disabled}
                  className="w-full accent-red-500"
                />
                <div className="flex justify-between text-xs text-gray-500 mt-1">
                  <span>$50</span>
                  <span>$500</span>
                </div>
              </div>

              {/* Minimum Edge */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Min Required Edge: {((localSettings.min_edge || 0.05) * 100).toFixed(0)}%
                </label>
                <input
                  type="range"
                  min="0.01"
                  max="0.20"
                  step="0.01"
                  value={localSettings.min_edge || 0.05}
                  onChange={(e) => updateSetting('min_edge', Number(e.target.value))}
                  disabled={disabled}
                  className="w-full accent-yellow-500"
                />
                <div className="flex justify-between text-xs text-gray-500 mt-1">
                  <span>1%</span>
                  <span>20%</span>
                </div>
                <p className="text-xs text-gray-500 mt-1">Only trade when predicted edge exceeds this threshold</p>
              </div>

              {/* Auto Exit on Resolution */}
              <div className="p-4 rounded-xl bg-black/30 border border-white/10">
                <div className="flex items-center justify-between">
                  <label className="text-sm font-medium text-gray-300">
                    🎯 Auto-Exit Before Resolution
                  </label>
                  <button
                    onClick={() => updateSetting('auto_exit_on_resolution', !localSettings.auto_exit_on_resolution)}
                    disabled={disabled}
                    className={`w-12 h-6 rounded-full transition-colors ${
                      localSettings.auto_exit_on_resolution ? 'bg-primary-500' : 'bg-gray-600'
                    }`}
                  >
                    <div className={`w-5 h-5 bg-white rounded-full transition-transform ${
                      localSettings.auto_exit_on_resolution ? 'translate-x-6' : 'translate-x-0.5'
                    }`} />
                  </button>
                </div>
                <p className="text-xs text-gray-500 mt-2">Exit positions before markets close to avoid resolution risk</p>
              </div>
            </>
          )}
        </div>

        <div className="p-6 border-t border-white/10 flex gap-3">
          <button
            onClick={onClose}
            className="flex-1 px-4 py-3 bg-white/5 text-white rounded-xl hover:bg-white/10 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={disabled}
            className="flex-1 px-4 py-3 bg-primary-500 text-black font-semibold rounded-xl hover:bg-primary-400 transition-colors disabled:opacity-50"
          >
            Save Settings
          </button>
        </div>

        {disabled && (
          <div className="px-6 pb-6 text-center text-sm text-yellow-400">
            ⚠️ Stop the bot to change settings
          </div>
        )}
      </div>
    </div>
  )
}
