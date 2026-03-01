import { useState, useMemo } from 'react'
import { Chessboard } from 'react-chessboard'
import { Chess, Square } from 'chess.js'
import { useGameStore } from '../../stores/gameStore'
import { useWebSocket } from '../../services/websocket'

export function ChessBoard() {
  const { fen, gameId, isAgentThinking, turn, whitePlayer, blackPlayer, isGameOver, result } = useGameStore()
  const { makeMove: wsMakeMove } = useWebSocket()
  const [moveFrom, setMoveFrom] = useState<Square | null>(null)
  const [optionSquares, setOptionSquares] = useState<Record<string, { background: string }>>({})

  const chess = useMemo(() => {
    try {
      return new Chess(fen)
    } catch {
      // If FEN is invalid (e.g. partial from detection), try normalizing
      try {
        const parts = fen.split(' ')
        const fullFen = parts.length < 6
          ? `${parts[0]} w - - 0 1`
          : fen
        return new Chess(fullFen)
      } catch {
        return new Chess() // fallback to starting position
      }
    }
  }, [fen])

  const isPlayerTurn = useMemo(() => {
    if (turn === 'white' && whitePlayer === 'human') return true
    if (turn === 'black' && blackPlayer === 'human') return true
    return false
  }, [turn, whitePlayer, blackPlayer])

  function getMoveOptions(square: Square) {
    const moves = chess.moves({ square, verbose: true })
    if (moves.length === 0) {
      setOptionSquares({})
      return false
    }

    const newSquares: Record<string, { background: string }> = {}
    moves.forEach((move) => {
      newSquares[move.to] = {
        background:
          chess.get(move.to as Square) && chess.get(move.to as Square)?.color !== chess.get(square)?.color
            ? 'radial-gradient(circle, rgba(0,0,0,.1) 85%, transparent 85%)'
            : 'radial-gradient(circle, rgba(0,0,0,.1) 25%, transparent 25%)',
      }
    })
    newSquares[square] = {
      background: 'rgba(255, 255, 0, 0.4)',
    }
    setOptionSquares(newSquares)
    return true
  }

  function onSquareClick(square: Square) {
    if (!isPlayerTurn || isAgentThinking || isGameOver) return

    // If clicking the same square, deselect
    if (moveFrom === square) {
      setMoveFrom(null)
      setOptionSquares({})
      return
    }

    // If we have a piece selected and clicking a valid move square
    if (moveFrom) {
      const moves = chess.moves({ square: moveFrom, verbose: true })
      const foundMove = moves.find((m) => m.from === moveFrom && m.to === square)

      if (foundMove) {
        // Handle promotion
        const promotion = foundMove.promotion || undefined

        if (gameId) {
          wsMakeMove(gameId, `${moveFrom}${square}${promotion || ''}`)
        }

        setMoveFrom(null)
        setOptionSquares({})
        return
      }
    }

    // Select a new piece
    const piece = chess.get(square)
    if (piece && piece.color === chess.turn()) {
      setMoveFrom(square)
      getMoveOptions(square)
    } else {
      setMoveFrom(null)
      setOptionSquares({})
    }
  }

  function onDrop(sourceSquare: Square, targetSquare: Square) {
    if (!isPlayerTurn || isAgentThinking || isGameOver) return false

    const moves = chess.moves({ square: sourceSquare, verbose: true })
    const foundMove = moves.find((m) => m.from === sourceSquare && m.to === targetSquare)

    if (!foundMove) return false

    const promotion = foundMove.promotion || undefined

    if (gameId) {
      wsMakeMove(gameId, `${sourceSquare}${targetSquare}${promotion || ''}`)
    }

    setMoveFrom(null)
    setOptionSquares({})
    return true
  }

  return (
    <div className="relative">
      <div className="rounded-lg overflow-hidden shadow-2xl">
        <Chessboard
          id="chess-board"
          position={fen}
          onSquareClick={onSquareClick}
          onPieceDrop={onDrop}
          boardWidth={480}
          customSquareStyles={optionSquares}
          customBoardStyle={{
            borderRadius: '4px',
          }}
          customDarkSquareStyle={{ backgroundColor: '#b58863' }}
          customLightSquareStyle={{ backgroundColor: '#f0d9b5' }}
          arePiecesDraggable={isPlayerTurn && !isAgentThinking && !isGameOver}
        />
      </div>

      {/* Turn indicator */}
      <div className="mt-4 text-center">
        <span className="text-slate-400">Turn: </span>
        <span className={`font-semibold ${turn === 'white' ? 'text-white' : 'text-slate-300'}`}>
          {turn.charAt(0).toUpperCase() + turn.slice(1)}
          {isPlayerTurn ? ' (You)' : ' (Agent)'}
        </span>
      </div>

      {/* Agent thinking indicator */}
      {isAgentThinking && (
        <div className="absolute inset-0 bg-black/30 flex items-center justify-center rounded-lg">
          <div className="bg-slate-800 px-6 py-4 rounded-lg shadow-xl">
            <div className="flex items-center space-x-3">
              <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-400"></div>
              <span className="text-white">Agent is thinking...</span>
            </div>
          </div>
        </div>
      )}

      {/* Game over overlay */}
      {isGameOver && (
        <div className="absolute inset-0 bg-black/50 flex items-center justify-center rounded-lg">
          <div className="bg-slate-800 px-8 py-6 rounded-lg shadow-xl text-center">
            <h3 className="text-2xl font-bold text-white mb-2">Game Over</h3>
            <p className="text-slate-300 text-lg">
              {result === '1-0' && 'White wins!'}
              {result === '0-1' && 'Black wins!'}
              {result === '1/2-1/2' && 'Draw!'}
              {!result && 'Game ended'}
            </p>
          </div>
        </div>
      )}
    </div>
  )
}
