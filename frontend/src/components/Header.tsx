'use client'

interface HeaderProps {
  isRunning: boolean
}

export function Header({ isRunning }: HeaderProps) {
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
    </header>
  )
}
