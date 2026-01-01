'use client'

import { BotStatus, formatCurrency } from '@/lib/api'
import { Play, Square, Activity, TrendingUp, Target, Clock } from 'lucide-react'

interface SidebarProps {
  status?: BotStatus
  activities: string[]
  onStart: () => void
  onStop: () => void
  isStarting: boolean
  isStopping: boolean
}

export function Sidebar({ 
  status, 
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
            value={formatCurrency(status?.total_pnl ?? 0)}
            color={status?.total_pnl && status.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}
          />
          <StatItem
            icon={Target}
            label="Win Rate"
            value={`${Math.round((status?.win_rate ?? 0) * 100)}%`}
            color="text-purple-400"
          />
          <StatItem
            icon={Clock}
            label="Positions"
            value={status?.active_positions?.toString() ?? '0'}
            color="text-yellow-400"
          />
        </div>
      </div>

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
