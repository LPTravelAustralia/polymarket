'use client'

import { BotStatus, Portfolio, formatCurrency } from '@/lib/api'
import { PnLChart } from './PnLChart'
import { Play, Square, Activity, TrendingUp, Target, Clock, Wallet } from 'lucide-react'

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
}

export function Sidebar({ 
  status, 
  portfolio,
  equityHistory,
  activities, 
  onStart, 
  onStop, 
  isStarting, 
  isStopping 
}: SidebarProps) {
  return (
    <div className="space-y-6">
      {/* Bot Controls */}
      <div className="bg-white/5 rounded-2xl p-6 border border-white/10">
        <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <span className="text-xl">🎮</span> Bot Controls
        </h2>

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
            icon={Activity}
            label="Trades"
            value={status?.trades_today?.toString() ?? '0'}
            color="text-blue-400"
          />
          <StatItem
            icon={TrendingUp}
            label="P&L"
            value={formatCurrency(portfolio?.total_pnl ?? status?.total_pnl ?? 0)}
            color={(portfolio?.total_pnl ?? status?.total_pnl ?? 0) >= 0 ? 'text-green-400' : 'text-red-400'}
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
              <div key={pos.market_id} className="bg-black/30 rounded-xl p-3 text-sm">
                <div className="font-medium truncate mb-1" title={pos.question}>
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
            {portfolio.closed_trades.slice(0, 10).map((trade, idx) => (
              <div key={idx} className="bg-black/30 rounded-xl p-3 text-sm">
                <div className="flex justify-between items-center">
                  <span className="truncate flex-1 mr-2" title={trade.question}>
                    {trade.question.slice(0, 30)}...
                  </span>
                  <span className={`px-2 py-0.5 rounded text-xs font-semibold ${
                    trade.reason === 'TP' ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'
                  }`}>
                    {trade.reason}
                  </span>
                </div>
                <div className="flex justify-between text-xs text-gray-400 mt-1">
                  <span>{trade.side.toUpperCase()} ${trade.size}</span>
                  <span className={trade.pnl >= 0 ? 'text-green-400' : 'text-red-400'}>
                    {trade.pnl >= 0 ? '+' : ''}{trade.pnl.toFixed(2)}
                  </span>
                </div>
              </div>
            ))}
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
