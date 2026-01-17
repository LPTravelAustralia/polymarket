'use client'

import { useState, useEffect, useCallback } from 'react'
import { X, TrendingUp, TrendingDown, AlertCircle, CheckCircle, Bell } from 'lucide-react'

export interface Toast {
  id: string
  type: 'trade' | 'close' | 'info' | 'success' | 'error'
  title: string
  message: string
  duration?: number
}

interface ToastProps {
  toast: Toast
  onDismiss: (id: string) => void
}

function ToastItem({ toast, onDismiss }: ToastProps) {
  useEffect(() => {
    if (toast.duration) {
      const timer = setTimeout(() => onDismiss(toast.id), toast.duration)
      return () => clearTimeout(timer)
    }
  }, [toast.id, toast.duration, onDismiss])

  const getIcon = () => {
    switch (toast.type) {
      case 'trade':
        return <TrendingUp className="w-5 h-5 text-green-400" />
      case 'close':
        return <TrendingDown className="w-5 h-5 text-orange-400" />
      case 'success':
        return <CheckCircle className="w-5 h-5 text-green-400" />
      case 'error':
        return <AlertCircle className="w-5 h-5 text-red-400" />
      default:
        return <Bell className="w-5 h-5 text-blue-400" />
    }
  }

  const getBorderColor = () => {
    switch (toast.type) {
      case 'trade':
        return 'border-green-500/50'
      case 'close':
        return 'border-orange-500/50'
      case 'success':
        return 'border-green-500/50'
      case 'error':
        return 'border-red-500/50'
      default:
        return 'border-blue-500/50'
    }
  }

  return (
    <div 
      className={`bg-gray-900/95 backdrop-blur-sm border ${getBorderColor()} rounded-xl p-4 shadow-xl animate-slide-in flex gap-3 items-start max-w-sm`}
    >
      <div className="flex-shrink-0 mt-0.5">{getIcon()}</div>
      <div className="flex-1 min-w-0">
        <p className="font-medium text-sm text-white">{toast.title}</p>
        <p className="text-xs text-gray-400 mt-0.5 truncate">{toast.message}</p>
      </div>
      <button 
        onClick={() => onDismiss(toast.id)}
        className="flex-shrink-0 p-1 hover:bg-white/10 rounded transition-colors"
      >
        <X className="w-4 h-4 text-gray-500" />
      </button>
    </div>
  )
}

interface ToastContainerProps {
  toasts: Toast[]
  onDismiss: (id: string) => void
}

export function ToastContainer({ toasts, onDismiss }: ToastContainerProps) {
  if (toasts.length === 0) return null

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2">
      {toasts.map(toast => (
        <ToastItem key={toast.id} toast={toast} onDismiss={onDismiss} />
      ))}
    </div>
  )
}

// Hook for managing toasts
export function useToasts() {
  const [toasts, setToasts] = useState<Toast[]>([])

  const addToast = useCallback((toast: Omit<Toast, 'id'>) => {
    const id = Math.random().toString(36).substring(7)
    setToasts(prev => [...prev, { ...toast, id, duration: toast.duration ?? 5000 }])
  }, [])

  const dismissToast = useCallback((id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id))
  }, [])

  // Helper functions for common toast types
  const showTradeNotification = useCallback((side: string, question: string, amount: number) => {
    addToast({
      type: 'trade',
      title: `📈 New Position: ${side.toUpperCase()}`,
      message: `$${amount} on ${question.slice(0, 40)}...`,
      duration: 4000,
    })
  }, [addToast])

  const showCloseNotification = useCallback((reason: string, question: string, pnl: number) => {
    const emoji = pnl >= 0 ? '🟢' : '🔴'
    const reasonText = reason === 'TP' ? 'Take Profit' : reason === 'SL' ? 'Stop Loss' : 'Resolved'
    addToast({
      type: 'close',
      title: `${emoji} Position Closed (${reasonText})`,
      message: `${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)} on ${question.slice(0, 35)}...`,
      duration: 6000,
    })
  }, [addToast])

  const showSuccess = useCallback((title: string, message: string) => {
    addToast({ type: 'success', title, message, duration: 3000 })
  }, [addToast])

  const showError = useCallback((title: string, message: string) => {
    addToast({ type: 'error', title, message, duration: 5000 })
  }, [addToast])

  return {
    toasts,
    addToast,
    dismissToast,
    showTradeNotification,
    showCloseNotification,
    showSuccess,
    showError,
  }
}
