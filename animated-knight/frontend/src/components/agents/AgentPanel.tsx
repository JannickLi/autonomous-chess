import { useGameStore } from '../../stores/gameStore'
import { PieceAvatar } from './PieceAvatar'

export function AgentPanel() {
  const { strategy, supervisorModel, agentModel } = useGameStore()

  const strategyInfo = {
    supervisor: {
      name: 'Supervisor',
      description: 'A supervisor agent analyzes the position and makes the final decision.',
      icon: '\uD83D\uDC54',
    },
    hybrid: {
      name: 'Democratic',
      description: 'Supervisor proposes candidates, then all pieces vote based on their personality.',
      icon: '\uD83D\uDDF3\uFE0F',
    },
  }

  const currentStrategy = strategyInfo[strategy as keyof typeof strategyInfo] || strategyInfo.hybrid

  const votingPieces = [
    { type: 'king', name: 'King', weight: 10 },
    { type: 'queen', name: 'Queen', weight: 9 },
    { type: 'rook', name: 'Rook', weight: 5 },
    { type: 'bishop', name: 'Bishop', weight: 3 },
    { type: 'knight', name: 'Knight', weight: 3 },
    { type: 'pawn', name: 'Pawn', weight: 1 },
  ]

  return (
    <div className="bg-slate-800/80 backdrop-blur rounded-2xl border border-slate-700/50 p-4">
      <h3 className="text-base font-semibold text-white mb-4">Agent Configuration</h3>

      <div className="space-y-4">
        {/* Current Strategy */}
        <div className="bg-slate-700/40 rounded-xl p-3 border border-slate-600/20">
          <div className="flex items-center space-x-2 mb-2">
            <span className="text-2xl">{currentStrategy.icon}</span>
            <span className="font-medium text-white">{currentStrategy.name}</span>
          </div>
          <p className="text-sm text-slate-400">{currentStrategy.description}</p>
          <div className="text-xs text-slate-500 mt-2 space-y-1">
            <p>Supervisor: {supervisorModel}</p>
            <p>Agents: {agentModel}</p>
          </div>
        </div>

        {/* Voting weights with piece avatars */}
        {strategy === 'hybrid' && (
          <div>
            <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Voting Power</h4>
            <div className="grid grid-cols-3 gap-2">
              {votingPieces.map(({ type, name, weight }) => (
                <div key={name} className="bg-slate-700/40 rounded-xl p-2.5 flex flex-col items-center gap-1.5 border border-slate-600/20">
                  <PieceAvatar pieceType={type} color="white" size="sm" />
                  <div className="text-center">
                    <div className="text-[10px] text-slate-400">{name}</div>
                    <div className="text-xs text-white font-semibold">x{weight}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
