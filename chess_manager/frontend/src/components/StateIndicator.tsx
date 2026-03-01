import { useGameStore, GameStateValue } from '../stores/gameStore'

const STATE_CONFIG: Record<GameStateValue, { label: string; color: string; icon: string }> = {
  waiting: { label: 'Waiting', color: 'bg-slate-500', icon: '...' },
  human_turn: { label: 'Your Turn', color: 'bg-emerald-500', icon: '>' },
  validating: { label: 'Validating', color: 'bg-yellow-500', icon: '?' },
  agent_turn: { label: 'Agent Turn', color: 'bg-blue-500', icon: '<' },
  thinking: { label: 'Agent Thinking', color: 'bg-purple-500', icon: '*' },
  executing: { label: 'Robot Moving', color: 'bg-orange-500', icon: '!' },
  game_over: { label: 'Game Over', color: 'bg-red-500', icon: '#' },
}

export function StateIndicator() {
  const { state, turn, isCheck, isGameOver, result, legalMovesCount } = useGameStore()
  const config = STATE_CONFIG[state]

  return (
    <div className="bg-slate-800 rounded-lg p-4">
      <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-3">
        Game State
      </h2>

      {/* State badge */}
      <div className="flex items-center gap-3 mb-4">
        <span className={`w-3 h-3 rounded-full ${config.color} ${
          state === 'thinking' || state === 'executing' ? 'animate-pulse' : ''
        }`} />
        <span className="text-lg font-bold text-white">{config.label}</span>
      </div>

      {/* State pipeline */}
      <div className="flex gap-1 mb-4">
        {Object.entries(STATE_CONFIG).map(([key, cfg]) => (
          <div
            key={key}
            className={`h-1.5 flex-1 rounded-full transition-colors ${
              key === state ? cfg.color : 'bg-slate-700'
            }`}
            title={cfg.label}
          />
        ))}
      </div>

      {/* Details */}
      <div className="space-y-2 text-sm">
        <div className="flex justify-between">
          <span className="text-slate-400">Turn</span>
          <span className="text-white font-medium capitalize">{turn}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-slate-400">Legal Moves</span>
          <span className="text-white font-medium">{legalMovesCount}</span>
        </div>
        {isCheck && (
          <div className="flex justify-between">
            <span className="text-slate-400">Status</span>
            <span className="text-red-400 font-bold">CHECK</span>
          </div>
        )}
        {isGameOver && result && (
          <div className="flex justify-between">
            <span className="text-slate-400">Result</span>
            <span className="text-yellow-400 font-bold">{result}</span>
          </div>
        )}
      </div>
    </div>
  )
}
