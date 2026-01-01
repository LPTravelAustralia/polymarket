'use client'

import { useState } from 'react'
import { Settings, X } from 'lucide-react'

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
}

interface SettingsPanelProps {
  isOpen: boolean
  onClose: () => void
  settings: BotSettings
  onSave: (settings: BotSettings) => void
  disabled?: boolean
}

export function SettingsPanel({ isOpen, onClose, settings, onSave, disabled }: SettingsPanelProps) {
  const [localSettings, setLocalSettings] = useState<BotSettings>(settings)

  if (!isOpen) return null

  const handleSave = () => {
    onSave(localSettings)
    onClose()
  }

  const updateSetting = <K extends keyof BotSettings>(key: K, value: BotSettings[K]) => {
    setLocalSettings(prev => ({ ...prev, [key]: value }))
  }

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-gray-900 rounded-2xl border border-white/10 w-full max-w-md max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between p-6 border-b border-white/10">
          <h2 className="text-xl font-semibold flex items-center gap-2">
            <Settings className="w-5 h-5" />
            Bot Settings
          </h2>
          <button onClick={onClose} className="p-2 hover:bg-white/10 rounded-lg transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-6 space-y-5">
          {/* Agent Selection */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">Strategy</label>
            <select
              value={localSettings.agent}
              onChange={(e) => updateSetting('agent', e.target.value)}
              disabled={disabled}
              className="w-full bg-black/30 border border-white/10 rounded-xl px-4 py-3 text-white focus:outline-none focus:ring-2 focus:ring-primary-500"
            >
              <option value="momentum">Momentum</option>
              <option value="ai">AI Superforecaster</option>
            </select>
          </div>

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

          {/* Global Cap */}
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

          {/* Drawdown Limit */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              Drawdown Limit: ${localSettings.drawdown_limit}
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
