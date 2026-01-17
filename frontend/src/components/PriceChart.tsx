'use client'

import { useEffect, useRef, useState } from 'react'
import { BarChart3, TrendingUp, TrendingDown, Minus } from 'lucide-react'

interface PricePoint {
  timestamp: number
  price: number
}

interface OrderBookLevel {
  price: number
  size: number
}

interface OrderBook {
  bids: OrderBookLevel[]
  asks: OrderBookLevel[]
}

interface PriceChartProps {
  marketId: string
  yesPrice: number
  noPrice: number
  priceHistory?: PricePoint[]
  orderBook?: OrderBook
  className?: string
}

// Generate simulated price history for demo
function generatePriceHistory(currentPrice: number, points: number = 24): PricePoint[] {
  const history: PricePoint[] = []
  const now = Date.now()
  let price = currentPrice + (Math.random() - 0.5) * 0.2
  
  for (let i = points; i >= 0; i--) {
    // Random walk with mean reversion
    const change = (Math.random() - 0.5) * 0.03
    const meanReversion = (currentPrice - price) * 0.1
    price = Math.max(0.01, Math.min(0.99, price + change + meanReversion))
    
    history.push({
      timestamp: now - i * 3600000, // hourly
      price: price
    })
  }
  
  // Ensure last point is current price
  history[history.length - 1].price = currentPrice
  
  return history
}

// Generate simulated order book for demo
function generateOrderBook(yesPrice: number): OrderBook {
  const bids: OrderBookLevel[] = []
  const asks: OrderBookLevel[] = []
  
  // Generate bids (below current price)
  for (let i = 1; i <= 5; i++) {
    const price = Math.max(0.01, yesPrice - i * 0.01)
    const size = Math.floor(1000 + Math.random() * 5000)
    bids.push({ price, size })
  }
  
  // Generate asks (above current price)
  for (let i = 1; i <= 5; i++) {
    const price = Math.min(0.99, yesPrice + i * 0.01)
    const size = Math.floor(1000 + Math.random() * 5000)
    asks.push({ price, size })
  }
  
  return { bids, asks: asks.reverse() }
}

export function PriceChart({ 
  marketId, 
  yesPrice, 
  noPrice, 
  priceHistory, 
  orderBook,
  className = ''
}: PriceChartProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [activeTab, setActiveTab] = useState<'chart' | 'orderbook'>('chart')
  const [timeframe, setTimeframe] = useState<'1h' | '24h' | '7d'>('24h')
  
  // Generate demo data if not provided
  const history = priceHistory || generatePriceHistory(yesPrice)
  const book = orderBook || generateOrderBook(yesPrice)
  
  // Calculate price change
  const priceChange = history.length >= 2 
    ? history[history.length - 1].price - history[0].price 
    : 0
  const priceChangePercent = history[0].price > 0 
    ? (priceChange / history[0].price) * 100 
    : 0
  
  // Draw chart on canvas
  useEffect(() => {
    if (activeTab !== 'chart') return
    const canvas = canvasRef.current
    if (!canvas) return
    
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    
    const dpr = window.devicePixelRatio || 1
    const rect = canvas.getBoundingClientRect()
    canvas.width = rect.width * dpr
    canvas.height = rect.height * dpr
    ctx.scale(dpr, dpr)
    
    const width = rect.width
    const height = rect.height
    const padding = { top: 10, right: 10, bottom: 20, left: 40 }
    const chartWidth = width - padding.left - padding.right
    const chartHeight = height - padding.top - padding.bottom
    
    // Clear canvas
    ctx.clearRect(0, 0, width, height)
    
    // Find min/max
    const prices = history.map(p => p.price)
    const minPrice = Math.min(...prices) - 0.02
    const maxPrice = Math.max(...prices) + 0.02
    const priceRange = maxPrice - minPrice
    
    // Draw grid
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.1)'
    ctx.lineWidth = 1
    
    for (let i = 0; i <= 4; i++) {
      const y = padding.top + (chartHeight * i) / 4
      ctx.beginPath()
      ctx.moveTo(padding.left, y)
      ctx.lineTo(width - padding.right, y)
      ctx.stroke()
      
      // Price label
      const price = maxPrice - (priceRange * i) / 4
      ctx.fillStyle = 'rgba(255, 255, 255, 0.5)'
      ctx.font = '10px Inter, sans-serif'
      ctx.textAlign = 'right'
      ctx.fillText(`${(price * 100).toFixed(0)}¢`, padding.left - 5, y + 3)
    }
    
    // Draw line chart
    ctx.beginPath()
    ctx.strokeStyle = priceChange >= 0 ? '#10b981' : '#ef4444'
    ctx.lineWidth = 2
    ctx.lineCap = 'round'
    ctx.lineJoin = 'round'
    
    history.forEach((point, i) => {
      const x = padding.left + (i / (history.length - 1)) * chartWidth
      const y = padding.top + chartHeight - ((point.price - minPrice) / priceRange) * chartHeight
      
      if (i === 0) {
        ctx.moveTo(x, y)
      } else {
        ctx.lineTo(x, y)
      }
    })
    ctx.stroke()
    
    // Draw area under line
    ctx.lineTo(padding.left + chartWidth, padding.top + chartHeight)
    ctx.lineTo(padding.left, padding.top + chartHeight)
    ctx.closePath()
    
    const gradient = ctx.createLinearGradient(0, padding.top, 0, padding.top + chartHeight)
    if (priceChange >= 0) {
      gradient.addColorStop(0, 'rgba(16, 185, 129, 0.3)')
      gradient.addColorStop(1, 'rgba(16, 185, 129, 0)')
    } else {
      gradient.addColorStop(0, 'rgba(239, 68, 68, 0.3)')
      gradient.addColorStop(1, 'rgba(239, 68, 68, 0)')
    }
    ctx.fillStyle = gradient
    ctx.fill()
    
    // Draw current price dot
    const lastPoint = history[history.length - 1]
    const lastX = padding.left + chartWidth
    const lastY = padding.top + chartHeight - ((lastPoint.price - minPrice) / priceRange) * chartHeight
    
    ctx.beginPath()
    ctx.arc(lastX, lastY, 4, 0, Math.PI * 2)
    ctx.fillStyle = priceChange >= 0 ? '#10b981' : '#ef4444'
    ctx.fill()
    
  }, [history, activeTab, priceChange])
  
  // Calculate max size for order book visualization
  const maxSize = Math.max(
    ...book.bids.map(b => b.size),
    ...book.asks.map(a => a.size)
  )
  
  return (
    <div className={`bg-black/30 rounded-xl border border-white/10 ${className}`}>
      {/* Header */}
      <div className="flex items-center justify-between p-3 border-b border-white/10">
        <div className="flex items-center gap-2">
          <BarChart3 className="w-4 h-4 text-gray-400" />
          <span className="text-sm font-medium">Price Analysis</span>
        </div>
        <div className="flex gap-1">
          <button
            onClick={() => setActiveTab('chart')}
            className={`px-3 py-1 text-xs rounded-lg transition-colors ${
              activeTab === 'chart' 
                ? 'bg-primary-500 text-black' 
                : 'bg-white/5 text-gray-400 hover:text-white'
            }`}
          >
            Chart
          </button>
          <button
            onClick={() => setActiveTab('orderbook')}
            className={`px-3 py-1 text-xs rounded-lg transition-colors ${
              activeTab === 'orderbook' 
                ? 'bg-primary-500 text-black' 
                : 'bg-white/5 text-gray-400 hover:text-white'
            }`}
          >
            Order Book
          </button>
        </div>
      </div>
      
      {/* Chart Tab */}
      {activeTab === 'chart' && (
        <div className="p-3">
          {/* Price Info */}
          <div className="flex items-center justify-between mb-3">
            <div>
              <span className="text-2xl font-bold">{(yesPrice * 100).toFixed(1)}¢</span>
              <span className="text-gray-400 text-sm ml-2">YES</span>
            </div>
            <div className={`flex items-center gap-1 text-sm ${
              priceChange >= 0 ? 'text-green-400' : 'text-red-400'
            }`}>
              {priceChange > 0 ? <TrendingUp className="w-4 h-4" /> : 
               priceChange < 0 ? <TrendingDown className="w-4 h-4" /> : 
               <Minus className="w-4 h-4" />}
              <span>{priceChangePercent >= 0 ? '+' : ''}{priceChangePercent.toFixed(1)}%</span>
            </div>
          </div>
          
          {/* Timeframe buttons */}
          <div className="flex gap-1 mb-3">
            {(['1h', '24h', '7d'] as const).map(tf => (
              <button
                key={tf}
                onClick={() => setTimeframe(tf)}
                className={`px-2 py-1 text-xs rounded transition-colors ${
                  timeframe === tf 
                    ? 'bg-white/20 text-white' 
                    : 'text-gray-500 hover:text-white'
                }`}
              >
                {tf}
              </button>
            ))}
          </div>
          
          {/* Canvas Chart */}
          <canvas 
            ref={canvasRef}
            className="w-full h-32"
            style={{ width: '100%', height: '128px' }}
          />
        </div>
      )}
      
      {/* Order Book Tab */}
      {activeTab === 'orderbook' && (
        <div className="p-3">
          {/* Spread indicator */}
          <div className="text-center mb-3">
            <span className="text-xs text-gray-400">Spread: </span>
            <span className="text-sm font-medium text-yellow-400">
              {((book.asks[book.asks.length - 1]?.price || 0) - (book.bids[0]?.price || 0)).toFixed(2)}
            </span>
          </div>
          
          {/* Asks (Sells) */}
          <div className="space-y-1 mb-2">
            {book.asks.map((ask, i) => (
              <div key={`ask-${i}`} className="relative flex justify-between text-xs py-1 px-2">
                <div 
                  className="absolute inset-0 bg-red-500/20 rounded"
                  style={{ width: `${(ask.size / maxSize) * 100}%`, right: 0, left: 'auto' }}
                />
                <span className="relative text-gray-400">${(ask.size).toLocaleString()}</span>
                <span className="relative text-red-400">{(ask.price * 100).toFixed(1)}¢</span>
              </div>
            ))}
          </div>
          
          {/* Current Price */}
          <div className="py-2 px-2 bg-white/5 rounded text-center mb-2">
            <span className="text-sm font-bold">{(yesPrice * 100).toFixed(1)}¢</span>
          </div>
          
          {/* Bids (Buys) */}
          <div className="space-y-1">
            {book.bids.map((bid, i) => (
              <div key={`bid-${i}`} className="relative flex justify-between text-xs py-1 px-2">
                <div 
                  className="absolute inset-0 bg-green-500/20 rounded"
                  style={{ width: `${(bid.size / maxSize) * 100}%` }}
                />
                <span className="relative text-green-400">{(bid.price * 100).toFixed(1)}¢</span>
                <span className="relative text-gray-400">${(bid.size).toLocaleString()}</span>
              </div>
            ))}
          </div>
          
          {/* Legend */}
          <div className="flex justify-between mt-3 text-xs text-gray-500">
            <span>🟢 Buy Orders</span>
            <span>🔴 Sell Orders</span>
          </div>
        </div>
      )}
    </div>
  )
}
