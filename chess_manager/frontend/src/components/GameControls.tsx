import { useState } from 'react'
import { useGameStore } from '../stores/gameStore'
import { sendCommand } from '../services/websocket'

export function GameControls() {
  const { state, isConnected, error } = useGameStore()
  const [moveInput, setMoveInput] = useState('')

  const canStart = state === 'waiting' || state === 'game_over'
  const canMove = state === 'human_turn'

  const handleStart = () => {
    sendCommand('start')
  }

  const handleMove = () => {
    const uci = moveInput.trim().toLowerCase()
    if (!uci) return
    sendCommand('move', { uci })
    setMoveInput('')
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleMove()
  }

  return (
    <div className="bg-slate-800 rounded-lg p-4 space-y-4">
      <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider">
        Controls
      </h2>

      {/* Error display */}
      {error && (
        <div className="bg-red-900/40 border border-red-700 rounded px-3 py-2 text-sm text-red-300">
          {error}
        </div>
      )}

      {/* Start/Reset */}
      <button
        onClick={handleStart}
        disabled={!isConnected || (!canStart)}
        className={`w-full py-2 px-4 rounded font-medium text-sm transition-colors ${
          canStart && isConnected
            ? 'bg-emerald-600 hover:bg-emerald-500 text-white'
            : 'bg-slate-700 text-slate-500 cursor-not-allowed'
        }`}
      >
        {state === 'game_over' ? 'New Game' : 'Start Game'}
      </button>

      {/* Move input */}
      <div>
        <label className="block text-xs text-slate-400 mb-1">Move (UCI)</label>
        <div className="flex gap-2">
          <input
            type="text"
            value={moveInput}
            onChange={(e) => setMoveInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="e.g. e2e4"
            disabled={!canMove}
            className={`flex-1 px-3 py-2 rounded text-sm bg-slate-700 border transition-colors ${
              canMove
                ? 'border-slate-600 text-white placeholder-slate-400 focus:border-blue-500 focus:outline-none'
                : 'border-slate-700 text-slate-500 placeholder-slate-600 cursor-not-allowed'
            }`}
          />
          <button
            onClick={handleMove}
            disabled={!canMove || !moveInput.trim()}
            className={`px-4 py-2 rounded font-medium text-sm transition-colors ${
              canMove && moveInput.trim()
                ? 'bg-blue-600 hover:bg-blue-500 text-white'
                : 'bg-slate-700 text-slate-500 cursor-not-allowed'
            }`}
          >
            Move
          </button>
        </div>
      </div>
    </div>
  )
}
