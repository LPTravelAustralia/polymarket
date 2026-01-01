'use client'

interface HeaderProps {
  isRunning: boolean
  wsConnected?: boolean
}

export function Header({ isRunning, wsConnected }: HeaderProps) {
  return (
    <header className="flex justify-between items-center py-6 border-b border-white/10 mb-8">
      <div className="flex items-center gap-3">
        <span className="text-3xl">🤖</span>
        <div>
          <h1 className="text-2xl font-bold">
            <span className="text-primary-500">Polymarket</span> Trading Bot
          </h1>
          <p className="text-sm text-gray-400">AI-powered prediction market trading</p>
        </div>
      </div>

      <div className="flex items-center gap-3">
        {/* WebSocket Status */}
        <div className={`
          px-3 py-1.5 rounded-full text-xs font-medium flex items-center gap-1.5
          ${wsConnected 
            ? 'bg-blue-500/20 text-blue-400 border border-blue-500/30' 
            : 'bg-gray-500/20 text-gray-400 border border-gray-500/30'
          }
        `} title={wsConnected ? 'Real-time updates active' : 'Polling for updates'}>
          <span className={`w-1.5 h-1.5 rounded-full ${wsConnected ? 'bg-blue-400' : 'bg-gray-400'}`} />
          {wsConnected ? '⚡ Live' : '📡 Polling'}
        </div>

        {/* Bot Status */}
        <div className={`
          px-4 py-2 rounded-full text-sm font-medium flex items-center gap-2
          ${isRunning 
            ? 'bg-primary-500/20 text-primary-400 border border-primary-500/50' 
            : 'bg-red-500/20 text-red-400 border border-red-500/50'
          }
        `}>
          <span className={`w-2 h-2 rounded-full ${isRunning ? 'bg-primary-400 animate-pulse' : 'bg-red-400'}`} />
          {isRunning ? 'Running' : 'Stopped'}
        </div>
      </div>
    </header>
  )
}
