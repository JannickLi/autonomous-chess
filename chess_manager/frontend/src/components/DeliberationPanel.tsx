import { Chess } from 'chess.js'
import { useGameStore } from '../stores/gameStore'
import { PieceCharacter } from './PieceAvatar'

const PIECE_TYPE_MAP: Record<string, string> = {
  k: 'king', q: 'queen', r: 'rook',
  b: 'bishop', n: 'knight', p: 'pawn',
}

/** Derive piece type from FEN + UCI move (e.g. "f1h3" → look at f1 in FEN). */
function pieceTypeFromMove(fen: string, uciMove: string): string | null {
  try {
    const chess = new Chess(fen)
    const from = uciMove.slice(0, 2)
    const piece = chess.get(from as never)
    if (!piece) return null
    return PIECE_TYPE_MAP[piece.type] ?? null
  } catch {
    return null
  }
}

export function DeliberationPanel() {
  const { deliberation, state, fen, ttsSpeakingPiece, ttsStatus } = useGameStore()

  const isThinking = state === 'thinking'
  const isSpeaking = ttsStatus === 'speaking' && ttsSpeakingPiece

  // Debug: log deliberation data as it arrives
  console.debug('[DeliberationPanel] render', {
    state,
    fen,
    deliberation,
    ttsStatus,
    ttsSpeakingPiece,
    isSpeaking,
    isThinking,
  })

  // Determine the piece type to display — this should be the piece
  // "making the statement" (the agent), not necessarily the piece being moved.
  // 1. If TTS is speaking a known piece, use that
  // 2. First opinion with a known piece_type (the statement-maker)
  // 3. Derive from FEN + selected_move as fallback
  // 4. Default to "queen" as the supervisor stand-in
  const displayPiece = (() => {
    if (isSpeaking && ttsSpeakingPiece !== 'unknown') return ttsSpeakingPiece
    if (!deliberation) return null

    // The agent making the statement
    const knownOpinion = deliberation.opinions.find(
      (op) => op.piece_type && op.piece_type !== 'unknown'
    )
    if (knownOpinion) return knownOpinion.piece_type

    // Fallback: derive from the move itself
    if (deliberation.selected_move) {
      const derived = pieceTypeFromMove(fen, deliberation.selected_move)
      if (derived) {
        console.debug('[DeliberationPanel] derived piece from FEN:', derived)
        return derived
      }
    }

    // Last resort: queen as supervisor stand-in
    return 'queen'
  })()

  // Get the first opinion's reasoning to display (they all describe the selected move)
  const displayReasoning = deliberation?.opinions?.[0]?.reasoning ?? null

  console.debug('[DeliberationPanel] displayPiece:', displayPiece, 'reasoning:', displayReasoning)

  return (
    <div className="bg-slate-800 rounded-lg p-4">
      <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-3">
        Agent Deliberation
      </h2>

      {isThinking && !deliberation && (
        <div className="flex items-center gap-2 text-purple-400 text-sm">
          <span className="w-2 h-2 bg-purple-400 rounded-full animate-pulse" />
          Agents are deliberating...
        </div>
      )}

      {!isThinking && !deliberation && (
        <p className="text-sm text-slate-500 italic">
          No deliberation yet. Waiting for agent turn.
        </p>
      )}

      {deliberation && (
        <div className="space-y-4">
          {/* Piece character — always shown when deliberation exists */}
          {displayPiece && (
            <div className="flex flex-col items-center py-2">
              <PieceCharacter pieceType={displayPiece} isSpeaking={!!isSpeaking} />
              <div className="mt-3 w-full">
                <div className="relative bg-slate-700/50 rounded-xl px-4 py-3">
                  {/* Speech bubble arrow */}
                  <div className="absolute -top-2 left-1/2 -translate-x-1/2 w-4 h-4 bg-slate-700/50 rotate-45" />
                  <div className="relative">
                    <span className="text-xs font-mono text-emerald-400 block mb-1">
                      suggests {deliberation.selected_move}
                    </span>
                    {displayReasoning && (
                      <p className="text-sm text-slate-300 italic leading-relaxed">
                        &ldquo;{displayReasoning}&rdquo;
                      </p>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
