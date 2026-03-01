import { Chessboard } from 'react-chessboard'
import { useGameStore } from '../stores/gameStore'

export function ChessBoard() {
  const { fen, state, isCheck, isGameOver } = useGameStore()

  const isThinking = state === 'thinking' || state === 'executing'

  return (
    <div className="relative">
      {/* Overlay for non-interactive states */}
      {isThinking && (
        <div className="absolute inset-0 z-10 flex items-center justify-center bg-black/30 rounded-lg">
          <div className="bg-slate-800/90 px-4 py-2 rounded-lg">
            <span className="text-white text-sm font-medium">
              {state === 'thinking' ? 'Agent thinking...' : 'Robot moving...'}
            </span>
          </div>
        </div>
      )}

      {isGameOver && (
        <div className="absolute inset-0 z-10 flex items-center justify-center bg-black/40 rounded-lg">
          <div className="bg-slate-800/90 px-6 py-3 rounded-lg text-center">
            <span className="text-yellow-400 text-lg font-bold block">Game Over</span>
          </div>
        </div>
      )}

      {/* Check glow */}
      <div className={`rounded-lg ${isCheck ? 'ring-2 ring-red-500 ring-opacity-75' : ''}`}>
        <Chessboard
          position={fen}
          boardWidth={400}
          arePiecesDraggable={false}
          customDarkSquareStyle={{ backgroundColor: '#b58863' }}
          customLightSquareStyle={{ backgroundColor: '#f0d9b5' }}
        />
      </div>
    </div>
  )
}
