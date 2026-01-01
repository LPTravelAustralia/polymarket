'use client'

interface PnLChartProps {
  data: { timestamp: string; pnl: number }[]
}

export function PnLChart({ data }: PnLChartProps) {
  if (!data || data.length < 2) {
    return (
      <div className="h-20 flex items-center justify-center text-gray-500 text-sm">
        Collecting data...
      </div>
    )
  }

  const pnls = data.map(d => d.pnl)
  const min = Math.min(...pnls)
  const max = Math.max(...pnls)
  const range = max - min || 1

  // Normalize to 0-100 for SVG
  const normalize = (val: number) => 100 - ((val - min) / range) * 80 - 10

  // Create path
  const width = 280
  const stepX = width / (data.length - 1)
  
  const points = data.map((d, i) => `${i * stepX},${normalize(d.pnl)}`).join(' ')
  const pathD = `M ${points.split(' ').join(' L ')}`
  
  // Gradient color based on final PnL
  const finalPnl = pnls[pnls.length - 1]
  const isPositive = finalPnl >= 0
  const strokeColor = isPositive ? '#22c55e' : '#ef4444'
  const fillColor = isPositive ? 'rgba(34, 197, 94, 0.1)' : 'rgba(239, 68, 68, 0.1)'

  // Create fill path
  const fillPath = `${pathD} L ${width},100 L 0,100 Z`

  return (
    <div className="h-20 w-full">
      <svg viewBox={`0 0 ${width} 100`} className="w-full h-full">
        {/* Grid lines */}
        <line x1="0" y1="50" x2={width} y2="50" stroke="rgba(255,255,255,0.1)" strokeDasharray="4" />
        
        {/* Fill */}
        <path d={fillPath} fill={fillColor} />
        
        {/* Line */}
        <path d={pathD} fill="none" stroke={strokeColor} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        
        {/* Current value dot */}
        <circle cx={width} cy={normalize(finalPnl)} r="4" fill={strokeColor} />
      </svg>
      
      {/* Labels */}
      <div className="flex justify-between text-xs text-gray-500 mt-1">
        <span>{data.length} samples</span>
        <span className={isPositive ? 'text-green-400' : 'text-red-400'}>
          {isPositive ? '+' : ''}{finalPnl.toFixed(2)}
        </span>
      </div>
    </div>
  )
}
