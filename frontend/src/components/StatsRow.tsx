'use client'

import { Market, BotStatus, formatCurrency } from '@/lib/api'
import { TrendingUp, DollarSign, BarChart3, Activity } from 'lucide-react'

interface StatsRowProps {
  markets: Market[]
  status?: BotStatus
}

export function StatsRow({ markets, status }: StatsRowProps) {
  const totalLiquidity = markets.reduce((sum, m) => sum + m.liquidity, 0)
  const totalVolume = markets.reduce((sum, m) => sum + m.volume, 0)

  const stats = [
    {
      label: 'Active Markets',
      value: markets.length.toString(),
      icon: BarChart3,
      color: 'text-blue-400',
    },
    {
      label: 'Total Liquidity',
      value: formatCurrency(totalLiquidity),
      icon: DollarSign,
      color: 'text-green-400',
    },
    {
      label: 'Total Volume',
      value: formatCurrency(totalVolume),
      icon: TrendingUp,
      color: 'text-purple-400',
    },
    {
      label: 'Trades Today',
      value: status?.trades_today?.toString() ?? '0',
      icon: Activity,
      color: 'text-primary-400',
    },
  ]

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
      {stats.map((stat) => (
        <div
          key={stat.label}
          className="bg-white/5 rounded-xl p-5 border border-white/10 hover:border-white/20 transition-colors"
        >
          <div className="flex items-center gap-3 mb-2">
            <stat.icon className={`w-5 h-5 ${stat.color}`} />
            <span className="text-sm text-gray-400">{stat.label}</span>
          </div>
          <div className="text-2xl font-bold">{stat.value}</div>
        </div>
      ))}
    </div>
  )
}
