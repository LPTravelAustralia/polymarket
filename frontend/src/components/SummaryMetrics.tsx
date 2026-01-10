'use client'

import { Summary24h } from '@/lib/api'
import { Activity, Zap, BarChart3 } from 'lucide-react'

interface SummaryMetricsProps {
  summary?: Summary24h
  isLoading?: boolean
}

export function SummaryMetrics({ summary, isLoading }: SummaryMetricsProps) {
  if (!summary && !isLoading) return null

  if (isLoading) {
    return (
      <div className="bg-white/5 rounded-2xl p-6 border border-white/10 animate-pulse">
        <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <span className="text-xl">📊</span> 24h Summary
        </h2>
        <div className="space-y-3">
          <div className="h-10 bg-white/10 rounded-lg"></div>
          <div className="h-10 bg-white/10 rounded-lg"></div>
        </div>
      </div>
    )
  }

  if (!summary) return null

  const formatMs = (ms: number | null): string => {
    if (ms === null) return '—'
    if (ms < 1000) return `${ms}ms`
    return `${(ms / 1000).toFixed(2)}s`
  }

  const formatEdge = (edge: number | null): string => {
    if (edge === null) return '—'
    return `${edge > 0 ? '+' : ''}${(edge * 100).toFixed(1)}%`
  }

  return (
    <div className="bg-white/5 rounded-2xl p-6 border border-white/10">
      <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
        <span className="text-xl">📊</span> 24h Summary
      </h2>

      {/* Trade Counts */}
      <div className="mb-4 grid grid-cols-3 gap-2 text-sm">
        <div className="bg-black/30 rounded-lg p-2">
          <div className="text-xs text-gray-400">Opened</div>
          <div className="text-lg font-bold">{summary.counts.trades_opened}</div>
        </div>
        <div className="bg-black/30 rounded-lg p-2">
          <div className="text-xs text-gray-400">Closed</div>
          <div className="text-lg font-bold">{summary.counts.trades_closed}</div>
        </div>
        <div className="bg-black/30 rounded-lg p-2">
          <div className="text-xs text-gray-400">Markets</div>
          <div className="text-lg font-bold">{summary.counts.distinct_markets}</div>
        </div>
      </div>

      {/* P&L */}
      <div className="mb-4 p-3 bg-black/30 rounded-lg border border-white/5">
        <div className="text-xs text-gray-400 mb-2">Realized P&L</div>
        <div className={`text-2xl font-bold ${summary.pnl.realized >= 0 ? 'text-green-400' : 'text-red-400'}`}>
          {summary.pnl.realized >= 0 ? '+' : ''}{summary.pnl.realized.toFixed(2)}
        </div>
      </div>

      {/* Metrics */}
      <div className="space-y-2 border-t border-white/10 pt-4">
        <div className="flex items-center justify-between text-sm">
          <span className="text-gray-400 flex items-center gap-2">
            <Zap className="w-4 h-4" />
            Avg Edge
          </span>
          <span className={`font-semibold ${(summary.metrics.avg_edge ?? 0) > 0 ? 'text-green-400' : 'text-gray-400'}`}>
            {formatEdge(summary.metrics.avg_edge)}
          </span>
        </div>
        <div className="flex items-center justify-between text-sm">
          <span className="text-gray-400 flex items-center gap-2">
            <Activity className="w-4 h-4" />
            Avg Decision Latency
          </span>
          <span className="font-semibold text-blue-400">
            {formatMs(summary.metrics.avg_decision_latency_ms)}
          </span>
        </div>
        <div className="flex items-center justify-between text-sm">
          <span className="text-gray-400 flex items-center gap-2">
            <BarChart3 className="w-4 h-4" />
            Avg Placement Latency
          </span>
          <span className="font-semibold text-purple-400">
            {formatMs(summary.metrics.avg_placement_latency_ms)}
          </span>
        </div>
      </div>

      {/* Stats */}
      {summary.stats.total_trades > 0 && (
        <div className="space-y-2 border-t border-white/10 mt-4 pt-4 text-xs">
          <div className="flex justify-between text-gray-400">
            <span>Win Rate</span>
            <span className="text-white font-semibold">{summary.stats.win_rate.toFixed(1)}%</span>
          </div>
          <div className="flex justify-between text-gray-400">
            <span>Profit Factor</span>
            <span className="text-white font-semibold">{summary.stats.profit_factor.toFixed(2)}</span>
          </div>
          <div className="flex justify-between text-gray-400">
            <span>Avg Win / Loss</span>
            <span className="text-white font-semibold">
              <span className="text-green-400">${summary.stats.avg_win.toFixed(2)}</span> / 
              <span className="text-red-400"> ${summary.stats.avg_loss.toFixed(2)}</span>
            </span>
          </div>
        </div>
      )}

      <div className="text-xs text-gray-500 mt-4 pt-2 border-t border-white/10">
        Updated: {new Date(summary.generated_at).toLocaleTimeString()}
      </div>
    </div>
  )
}
