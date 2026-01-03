'use client'

import { 
  AreaChart, 
  Area, 
  XAxis, 
  YAxis, 
  Tooltip, 
  ResponsiveContainer,
  ReferenceLine
} from 'recharts'

interface PnLDataPoint {
  timestamp: string
  pnl: number
  positions?: number
  exposure?: number
}

interface PnLChartProps {
  data: PnLDataPoint[]
  height?: number
  showAxes?: boolean
}

export function PnLChart({ data, height = 120, showAxes = false }: PnLChartProps) {
  if (!data || data.length < 2) {
    return (
      <div className={`flex items-center justify-center text-gray-500 text-sm`} style={{ height }}>
        <div className="text-center">
          <div className="text-2xl mb-1">📊</div>
          <div>Collecting data...</div>
          <div className="text-xs text-gray-600">PnL chart will appear here</div>
        </div>
      </div>
    )
  }

  // Process data for chart
  const chartData = data.map((d, i) => ({
    ...d,
    index: i,
    time: new Date(d.timestamp).toLocaleTimeString('en-US', { 
      hour: '2-digit', 
      minute: '2-digit' 
    }),
  }))

  const pnls = data.map(d => d.pnl)
  const min = Math.min(...pnls, 0)
  const max = Math.max(...pnls, 0)
  const finalPnl = pnls[pnls.length - 1]
  const isPositive = finalPnl >= 0
  
  // Calculate some stats
  const maxPnl = Math.max(...pnls)
  const minPnl = Math.min(...pnls)
  const maxDrawdown = maxPnl - minPnl

  // Colors
  const gradientId = `pnl-gradient-${isPositive ? 'green' : 'red'}`
  const strokeColor = isPositive ? '#22c55e' : '#ef4444'
  const gradientStart = isPositive ? 'rgba(34, 197, 94, 0.3)' : 'rgba(239, 68, 68, 0.3)'
  const gradientEnd = isPositive ? 'rgba(34, 197, 94, 0.0)' : 'rgba(239, 68, 68, 0.0)'

  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={chartData} margin={{ top: 5, right: 5, left: showAxes ? 40 : 5, bottom: 5 }}>
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={gradientStart} />
              <stop offset="100%" stopColor={gradientEnd} />
            </linearGradient>
          </defs>
          
          {/* Zero line */}
          <ReferenceLine y={0} stroke="rgba(255,255,255,0.2)" strokeDasharray="3 3" />
          
          {showAxes && (
            <>
              <XAxis 
                dataKey="time" 
                tick={{ fill: '#6b7280', fontSize: 10 }}
                axisLine={{ stroke: 'rgba(255,255,255,0.1)' }}
                tickLine={false}
                interval="preserveStartEnd"
              />
              <YAxis 
                tick={{ fill: '#6b7280', fontSize: 10 }}
                axisLine={{ stroke: 'rgba(255,255,255,0.1)' }}
                tickLine={false}
                tickFormatter={(val) => `$${val}`}
                domain={[min - Math.abs(min) * 0.1, max + Math.abs(max) * 0.1]}
              />
            </>
          )}
          
          <Tooltip
            contentStyle={{
              backgroundColor: 'rgba(17, 24, 39, 0.95)',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              borderRadius: '8px',
              padding: '8px 12px',
            }}
            labelStyle={{ color: '#9ca3af', fontSize: 11 }}
            formatter={(value: number) => [
              <span key="pnl" className={value >= 0 ? 'text-green-400' : 'text-red-400'}>
                {value >= 0 ? '+' : ''}${value.toFixed(2)}
              </span>,
              'PnL'
            ]}
            labelFormatter={(label) => `Time: ${label}`}
          />
          
          <Area
            type="monotone"
            dataKey="pnl"
            stroke={strokeColor}
            strokeWidth={2}
            fill={`url(#${gradientId})`}
            dot={false}
            activeDot={{ r: 4, fill: strokeColor }}
          />
        </AreaChart>
      </ResponsiveContainer>
      
      {/* Stats Bar */}
      <div className="flex justify-between items-center text-xs mt-1 px-1">
        <span className="text-gray-500">
          {chartData.length} pts
        </span>
        <div className="flex gap-3">
          <span className="text-gray-500">
            High: <span className="text-green-400">${maxPnl.toFixed(2)}</span>
          </span>
          <span className="text-gray-500">
            Low: <span className="text-red-400">${minPnl.toFixed(2)}</span>
          </span>
          <span className={`font-medium ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
            {isPositive ? '+' : ''}${finalPnl.toFixed(2)}
          </span>
        </div>
      </div>
    </div>
  )
}

// Larger chart version for dedicated PnL view
export function PnLChartLarge({ data }: { data: PnLDataPoint[] }) {
  return (
    <div className="bg-black/30 rounded-xl p-4 border border-white/10">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-medium text-gray-300">📈 Equity Curve</h3>
        {data.length > 0 && (
          <span className={`text-sm font-medium ${data[data.length - 1]?.pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            {data[data.length - 1]?.pnl >= 0 ? '+' : ''}${data[data.length - 1]?.pnl.toFixed(2)}
          </span>
        )}
      </div>
      <PnLChart data={data} height={200} showAxes />
    </div>
  )
}

