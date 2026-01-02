'use client'

import { Market, Analysis, formatCurrency, formatPercent } from '@/lib/api'
import { X, TrendingUp, TrendingDown, Minus, ExternalLink, Loader2 } from 'lucide-react'
import { PriceChart } from './PriceChart'

interface MarketModalProps {
  market: Market
  analysis?: Analysis
  isAnalyzing: boolean
  onClose: () => void
}

export function MarketModal({ market, analysis, isAnalyzing, onClose }: MarketModalProps) {
  const yesPercent = Math.round(market.yes_price * 100)
  const noPercent = Math.round(market.no_price * 100)

  const getRecommendationStyle = (rec?: string) => {
    switch (rec) {
      case 'BUY_YES':
        return { icon: TrendingUp, color: 'text-green-400', bg: 'bg-green-500/20', label: 'Buy YES' }
      case 'BUY_NO':
        return { icon: TrendingDown, color: 'text-red-400', bg: 'bg-red-500/20', label: 'Buy NO' }
      default:
        return { icon: Minus, color: 'text-yellow-400', bg: 'bg-yellow-500/20', label: 'Hold' }
    }
  }

  const recStyle = getRecommendationStyle(analysis?.recommendation)

  return (
    <div 
      className="fixed inset-0 bg-black/80 z-50 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div 
        className="bg-dark-200 rounded-2xl max-w-lg w-full max-h-[90vh] overflow-y-auto border border-white/10"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="p-6 border-b border-white/10">
          <div className="flex justify-between items-start gap-4">
            <h2 className="text-xl font-semibold pr-8">{market.question}</h2>
            <button 
              onClick={onClose}
              className="p-2 hover:bg-white/10 rounded-lg transition-colors shrink-0"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="p-6 space-y-6">
          {/* Current Prices */}
          <div className="grid grid-cols-2 gap-4">
            <div className="bg-green-500/10 border border-green-500/30 rounded-xl p-4 text-center">
              <div className="text-3xl font-bold text-green-400">{yesPercent}¢</div>
              <div className="text-sm text-gray-400 mt-1">Yes</div>
            </div>
            <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 text-center">
              <div className="text-3xl font-bold text-red-400">{noPercent}¢</div>
              <div className="text-sm text-gray-400 mt-1">No</div>
            </div>
          </div>

          {/* Market Stats */}
          <div className="bg-white/5 rounded-xl p-4 space-y-3">
            <div className="flex justify-between">
              <span className="text-gray-400">Liquidity</span>
              <span className="font-medium">{formatCurrency(market.liquidity)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-400">Volume</span>
              <span className="font-medium">{formatCurrency(market.volume)}</span>
            </div>
            {market.volume_24h && (
              <div className="flex justify-between">
                <span className="text-gray-400">24h Volume</span>
                <span className="font-medium">{formatCurrency(market.volume_24h)}</span>
              </div>
            )}
            {market.spread && (
              <div className="flex justify-between">
                <span className="text-gray-400">Spread</span>
                <span className="font-medium">{(market.spread * 100).toFixed(1)}%</span>
              </div>
            )}
            {market.end_date && (
              <div className="flex justify-between">
                <span className="text-gray-400">End Date</span>
                <span className="font-medium">
                  {new Date(market.end_date).toLocaleDateString()}
                </span>
              </div>
            )}
          </div>

          {/* Price Chart & Order Book */}
          <PriceChart
            marketId={market.id}
            yesPrice={market.yes_price}
            noPrice={market.no_price}
          />

          {/* AI Analysis */}
          <div className="bg-white/5 rounded-xl p-4">
            <h3 className="font-semibold mb-4 flex items-center gap-2">
              <span>🤖</span> AI Analysis
            </h3>

            {isAnalyzing ? (
              <div className="flex items-center justify-center gap-3 py-8 text-gray-400">
                <Loader2 className="w-5 h-5 animate-spin" />
                Analyzing market...
              </div>
            ) : analysis ? (
              <div className="space-y-4">
                {/* Recommendation */}
                <div className={`flex items-center gap-3 p-3 rounded-lg ${recStyle.bg}`}>
                  <recStyle.icon className={`w-6 h-6 ${recStyle.color}`} />
                  <div>
                    <div className={`font-semibold ${recStyle.color}`}>{recStyle.label}</div>
                    <div className="text-sm text-gray-400">
                      Confidence: {formatPercent(analysis.confidence)}
                    </div>
                  </div>
                </div>

                {/* Predicted vs Current */}
                <div className="grid grid-cols-2 gap-3">
                  <div className="bg-white/5 rounded-lg p-3 text-center">
                    <div className="text-sm text-gray-400 mb-1">Current</div>
                    <div className="text-xl font-bold">{yesPercent}%</div>
                  </div>
                  <div className="bg-primary-500/10 border border-primary-500/30 rounded-lg p-3 text-center">
                    <div className="text-sm text-gray-400 mb-1">Predicted</div>
                    <div className="text-xl font-bold text-primary-400">
                      {formatPercent(analysis.predicted_probability)}
                    </div>
                  </div>
                </div>

                {/* Edge */}
                <div className="flex justify-between items-center bg-white/5 rounded-lg p-3">
                  <span className="text-gray-400">Edge</span>
                  <span className={`font-bold ${analysis.edge > 0 ? 'text-green-400' : 'text-red-400'}`}>
                    {analysis.edge > 0 ? '+' : ''}{formatPercent(analysis.edge)}
                  </span>
                </div>

                {/* Reasoning */}
                <div className="text-sm text-gray-300 leading-relaxed">
                  {analysis.reasoning}
                </div>
              </div>
            ) : (
              <div className="text-gray-400 text-center py-4">
                Click analyze to get AI prediction
              </div>
            )}
          </div>

          {/* Actions */}
          <div className="flex gap-3">
            <a
              href={`https://polymarket.com/event/${market.slug || ''}`}
              target="_blank"
              rel="noopener noreferrer"
              className="flex-1 flex items-center justify-center gap-2 px-4 py-3 bg-primary-500 text-black font-semibold rounded-xl hover:bg-primary-400 transition-colors"
            >
              Trade on Polymarket
              <ExternalLink className="w-4 h-4" />
            </a>
          </div>
        </div>
      </div>
    </div>
  )
}
