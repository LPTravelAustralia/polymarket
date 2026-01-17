'use client'

import { useState } from 'react'
import { BotStatus, Portfolio, formatCurrency } from '@/lib/api'
import { PnLChart } from './PnLChart'
import { Play, Square, Activity, TrendingUp, Target, Clock, Wallet, Settings, X, Loader2 } from 'lucide-react'

interface EquityPoint {
  timestamp: string
  pnl: number
  positions: number
  exposure: number
}

interface SidebarProps {
  status?: BotStatus
  portfolio?: Portfolio
  equityHistory?: EquityPoint[]
  activities: string[]
  onStart: () => void
  onStop: () => void
  isStarting: boolean
  isStopping: boolean
  onOpenSettings?: () => void
  onClosePosition?: (marketId: string) => Promise<void>
}

export function Sidebar({ 
  status, 
  portfolio,
  equityHistory,
  activities, 
  onStart, 
  onStop, 
  isStarting, 
  isStopping,
  onOpenSettings,
  onClosePosition
}: SidebarProps) {
  const [closingPositions, setClosingPositions] = useState<Set<string>>(new Set())

  const handleClosePosition = async (marketId: string) => {
    if (!onClosePosition) return
    setClosingPositions(prev => new Set(prev).add(marketId))
    try {
      await onClosePosition(marketId)
    } finally {
      setClosingPositions(prev => {
        const next = new Set(prev)
        next.delete(marketId)
        return next
      })
    }
  }

  return (
    <div className="space-y-6">
      {/* Bot Controls */}
      <div className="bg-white/5 rounded-2xl p-6 border border-white/10">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <span className="text-xl">🎮</span> Bot Controls
          </h2>
          {onOpenSettings && (
            <button
              onClick={onOpenSettings}
              className="p-2 hover:bg-white/10 rounded-lg transition-colors"
              title="Settings"
            >
              <Settings className="w-5 h-5 text-gray-400" />
            </button>
          )}
        </div>

        <div className="flex gap-3">
          <button
            onClick={onStart}
            disabled={status?.running || isStarting}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-3 bg-primary-500 text-black font-semibold rounded-xl hover:bg-primary-400 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Play className="w-4 h-4" />
            {isStarting ? 'Starting...' : 'Start'}
          </button>
          <button
            onClick={onStop}
            disabled={!status?.running || isStopping}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-3 bg-red-500 text-white font-semibold rounded-xl hover:bg-red-400 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Square className="w-4 h-4" />
            {isStopping ? 'Stopping...' : 'Stop'}
          </button>
        </div>
      </div>

      {/* Statistics */}
      <div className="bg-white/5 rounded-2xl p-6 border border-white/10">
        <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <span className="text-xl">📈</span> Statistics
        </h2>

        <div className="grid grid-cols-2 gap-3">
          <StatItem
            icon={TrendingUp}
            label="Total P&L"
            value={formatCurrency(portfolio?.total_pnl ?? status?.total_pnl ?? 0)}
            color={(portfolio?.total_pnl ?? status?.total_pnl ?? 0) >= 0 ? 'text-green-400' : 'text-red-400'}
          />
          <StatItem
            icon={Target}
            label="Win Rate"
            value={portfolio?.stats ? `${portfolio.stats.win_rate}%` : '0%'}
            color="text-blue-400"
          />
          <StatItem
            icon={Wallet}
            label="Exposure"
            value={formatCurrency(portfolio?.exposure ?? 0)}
            color="text-purple-400"
          />
          <StatItem
            icon={Clock}
            label="Positions"
            value={portfolio?.positions?.length?.toString() ?? status?.active_positions?.toString() ?? '0'}
            color="text-yellow-400"
          />
        </div>

        {/* Detailed stats when available */}
        {portfolio?.stats && portfolio.stats.total_trades > 0 && (
          <div className="mt-4 pt-4 border-t border-white/10 grid grid-cols-2 gap-2 text-sm">
            <div className="text-gray-400">Trades: <span className="text-white">{portfolio.stats.total_trades}</span></div>
            <div className="text-gray-400">Wins: <span className="text-green-400">{portfolio.stats.winning_trades}</span> / Losses: <span className="text-red-400">{portfolio.stats.losing_trades}</span></div>
            <div className="text-gray-400">Avg Win: <span className="text-green-400">${portfolio.stats.avg_win}</span></div>
            <div className="text-gray-400">Avg Loss: <span className="text-red-400">${portfolio.stats.avg_loss}</span></div>
            <div className="text-gray-400">Best: <span className="text-green-400">${portfolio.stats.best_trade}</span></div>
            <div className="text-gray-400">Worst: <span className="text-red-400">${portfolio.stats.worst_trade}</span></div>
            <div className="col-span-2 text-gray-400">Profit Factor: <span className="text-white font-semibold">{portfolio.stats.profit_factor}</span></div>
          </div>
        )}
      </div>

      {/* P&L Chart */}
      {status?.running && (
        <div className="bg-white/5 rounded-2xl p-6 border border-white/10">
          <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <span className="text-xl">📊</span> P&L Chart
          </h2>
          <PnLChart data={equityHistory ?? []} />
        </div>
      )}

      {/* Open Positions */}
      {portfolio?.positions && portfolio.positions.length > 0 && (
        <div className="bg-white/5 rounded-2xl p-6 border border-white/10">
          <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <span className="text-xl">💼</span> Positions ({portfolio.positions.length})
          </h2>

          <div className="space-y-2 max-h-64 overflow-y-auto">
            {portfolio.positions.map((pos) => (
              <div key={pos.market_id} className="bg-black/30 rounded-xl p-3 text-sm relative group">
                {/* Close button */}
                {onClosePosition && (
                  <button
                    onClick={() => handleClosePosition(pos.market_id)}
                    disabled={closingPositions.has(pos.market_id)}
                    className="absolute top-2 right-2 p-1 rounded-lg bg-red-500/20 hover:bg-red-500/40 text-red-400 opacity-0 group-hover:opacity-100 transition-all disabled:opacity-50"
                    title="Close position"
                  >
                    {closingPositions.has(pos.market_id) ? (
                      <Loader2 className="w-3 h-3 animate-spin" />
                    ) : (
                      <X className="w-3 h-3" />
                    )}
                  </button>
                )}
                <div className="font-medium truncate mb-1 pr-6" title={pos.question}>
                  {pos.question.slice(0, 35)}...
                </div>
                <div className="flex justify-between text-xs text-gray-400">
                  <span className={pos.side === 'yes' ? 'text-green-400' : 'text-red-400'}>
                    {pos.side.toUpperCase()} ${pos.size}
                  </span>
                  <span className={pos.unrealized_pnl >= 0 ? 'text-green-400' : 'text-red-400'}>
                    {pos.unrealized_pnl >= 0 ? '+' : ''}{pos.unrealized_pnl.toFixed(2)}
                  </span>
                </div>
                <div className="flex justify-between text-xs text-gray-500 mt-1">
                  <span>Entry: {(pos.entry_price * 100).toFixed(1)}¢</span>
                  <span>Mark: {(pos.mark_price * 100).toFixed(1)}¢</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Closed Trades */}
      {portfolio?.closed_trades && portfolio.closed_trades.length > 0 && (
        <div className="bg-white/5 rounded-2xl p-6 border border-white/10">
          <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <span className="text-xl">📜</span> Closed Trades ({portfolio.closed_trades.length})
          </h2>
          
          <div className="text-sm mb-3 flex justify-between">
            <span className="text-gray-400">Realized P&L:</span>
            <span className={portfolio.realized_pnl >= 0 ? 'text-green-400 font-semibold' : 'text-red-400 font-semibold'}>
              {portfolio.realized_pnl >= 0 ? '+' : ''}{formatCurrency(portfolio.realized_pnl)}
            </span>
          </div>

          <div className="space-y-2 max-h-48 overflow-y-auto">
            {portfolio.closed_trades.slice(0, 10).map((trade, idx) => {
              const reasonStyles = {
                'TP': 'bg-green-500/20 text-green-400',
                'SL': 'bg-red-500/20 text-red-400',
                'RESOLVED_WIN': 'bg-yellow-500/20 text-yellow-400',
                'RESOLVED_LOSS': 'bg-gray-500/20 text-gray-400',
              }
              const reasonLabels = {
                'TP': 'TP',
                'SL': 'SL',
                'RESOLVED_WIN': '🏆 WON',
                'RESOLVED_LOSS': '💀 LOST',
              }
              return (
                <div key={idx} className="bg-black/30 rounded-xl p-3 text-sm">
                  <div className="flex justify-between items-center">
                    <span className="truncate flex-1 mr-2" title={trade.question}>
                      {trade.question.slice(0, 30)}...
                    </span>
                    <span className={`px-2 py-0.5 rounded text-xs font-semibold ${
                      reasonStyles[trade.reason as keyof typeof reasonStyles] || 'bg-gray-500/20 text-gray-400'
                    }`}>
                      {reasonLabels[trade.reason as keyof typeof reasonLabels] || trade.reason}
                    </span>
                  </div>
                  <div className="flex justify-between text-xs text-gray-400 mt-1">
                    <span>{trade.side.toUpperCase()} ${trade.size}</span>
                    <span className={trade.pnl >= 0 ? 'text-green-400' : 'text-red-400'}>
                      {trade.pnl >= 0 ? '+' : ''}{trade.pnl.toFixed(2)}
                    </span>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Activity Log */}
      <div className="bg-white/5 rounded-2xl p-6 border border-white/10">
        <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <span className="text-xl">📋</span> Activity
        </h2>

        <div className="bg-black/30 rounded-xl p-3 max-h-48 overflow-y-auto font-mono text-xs space-y-1">
          {activities.length === 0 ? (
            <div className="text-gray-500 py-2">No activity yet...</div>
          ) : (
            activities.map((activity, i) => (
              <div key={i} className="text-gray-400 py-1 border-b border-white/5 last:border-0">
                {activity}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}

function StatItem({ 
  icon: Icon, 
  label, 
  value, 
  color 
}: { 
  icon: any
  label: string
  value: string
  color: string 
}) {
  return (
    <div className="bg-white/5 rounded-xl p-4 text-center">
      <Icon className={`w-5 h-5 mx-auto mb-2 ${color}`} />
      <div className="text-lg font-bold">{value}</div>
      <div className="text-xs text-gray-400">{label}</div>
    </div>
  )
}
