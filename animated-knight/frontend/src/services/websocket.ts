import { create } from 'zustand'
import { useGameStore } from '../stores/gameStore'
import { useDeliberationStore } from '../stores/deliberationStore'
import { useExternalStore } from '../stores/externalStore'

interface WebSocketState {
  socket: WebSocket | null
  isConnected: boolean
  clientId: string | null
  _reconnectTimer: ReturnType<typeof setTimeout> | null
  _reconnectAttempts: number
  _lastGameId: string | undefined

  connect: (gameId?: string) => void
  disconnect: () => void
  send: (message: object) => void
  requestAgentMove: (gameId: string) => void
  makeMove: (gameId: string, move: string) => void
  requestRealTurn: (gameId: string) => void
}

const MAX_RECONNECT_DELAY = 10_000
const BASE_RECONNECT_DELAY = 500

export const useWebSocket = create<WebSocketState>((set, get) => ({
  socket: null,
  isConnected: false,
  clientId: null,
  _reconnectTimer: null,
  _reconnectAttempts: 0,
  _lastGameId: undefined,

  connect: (gameId?: string) => {
    const { socket, _reconnectTimer } = get()

    // Clear any pending reconnect
    if (_reconnectTimer) {
      clearTimeout(_reconnectTimer)
      set({ _reconnectTimer: null })
    }

    if (socket?.readyState === WebSocket.OPEN) {
      // Already connected, just subscribe to new game
      if (gameId) {
        get().send({ type: 'subscribe', game_id: gameId })
      }
      return
    }

    // Close stale socket if exists
    if (socket && socket.readyState !== WebSocket.CLOSED) {
      socket.close()
    }

    set({ _lastGameId: gameId })

    const wsUrl = gameId
      ? `ws://localhost:8000/ws/${gameId}`
      : 'ws://localhost:8000/ws'

    const ws = new WebSocket(wsUrl)

    ws.onopen = () => {
      console.log('WebSocket connected to', wsUrl)
      set({ socket: ws, isConnected: true, _reconnectAttempts: 0 })
    }

    ws.onclose = (event) => {
      set({ socket: null, isConnected: false, clientId: null })

      // Don't reconnect if intentionally disconnected (code 1000 with no reason = clean close)
      if (event.code === 1000 && event.reason === 'client_disconnect') return

      // Schedule reconnect with exponential backoff
      const { _reconnectAttempts } = get()
      const delay = Math.min(BASE_RECONNECT_DELAY * 2 ** _reconnectAttempts, MAX_RECONNECT_DELAY)
      console.log(`WebSocket closed (code ${event.code}), reconnecting in ${delay}ms (attempt ${_reconnectAttempts + 1})`)
      const timer = setTimeout(() => {
        set({ _reconnectAttempts: _reconnectAttempts + 1 })
        get().connect(get()._lastGameId)
      }, delay)
      set({ _reconnectTimer: timer })
    }

    ws.onerror = (error) => {
      console.error('WebSocket error:', error)
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        handleMessage(data)
      } catch (e) {
        console.error('WebSocket message parse error:', e, event.data)
      }
    }

    set({ socket: ws })
  },

  disconnect: () => {
    const { socket, _reconnectTimer } = get()
    if (_reconnectTimer) {
      clearTimeout(_reconnectTimer)
    }
    if (socket) {
      socket.close(1000, 'client_disconnect')
    }
    set({ socket: null, isConnected: false, clientId: null, _reconnectTimer: null, _reconnectAttempts: 0 })
  },

  send: (message: object) => {
    const { socket, isConnected } = get()
    console.log('WebSocket send:', { isConnected, hasSocket: !!socket, message })
    if (socket && isConnected) {
      socket.send(JSON.stringify(message))
    } else {
      console.warn('WebSocket not connected, cannot send message')
    }
  },

  requestAgentMove: (gameId: string) => {
    get().send({
      type: 'request_agent_move',
      game_id: gameId,
    })
  },

  makeMove: (gameId: string, move: string) => {
    get().send({
      type: 'make_move',
      game_id: gameId,
      move,
    })
  },

  requestRealTurn: (gameId: string) => {
    get().send({
      type: 'request_real_turn',
      game_id: gameId,
    })
  },
}))

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function handleMessage(data: { type: string; [key: string]: any }) {
  console.log('WebSocket received:', data)
  const gameStore = useGameStore.getState()
  const deliberationStore = useDeliberationStore.getState()
  const externalStore = useExternalStore.getState()

  switch (data.type) {
    case 'connected':
      useWebSocket.setState({ clientId: data.client_id as string })
      break

    case 'deliberation_started':
      deliberationStore.startDeliberation(data.data?.active_agents as string[] || [])
      gameStore.setAgentThinking(true)
      break

    case 'agent_thinking':
      // Agent is starting to think
      break

    case 'agent_thought':
      if (data.agent_id && data.data?.thought) {
        deliberationStore.addThought(
          data.agent_id as string,
          data.data.thought as string
        )
      }
      break

    case 'agent_proposal':
      if (data.data) {
        deliberationStore.addProposal({
          agentId: data.agent_id as string,
          choice: data.data.choice as string || 'A',  // A, B, or C
          description: data.data.description as string || data.data.reasoning as string,
          reasoning: data.data.reasoning as string,
          pieceImpacts: data.data.piece_impacts as Record<string, string> | undefined,
          move: data.data.move as string,  // UCI move (internal)
        })
      }
      break

    case 'voting_started':
      deliberationStore.setPhase('voting')
      break

    case 'vote_cast':
      if (data.data) {
        deliberationStore.addVote({
          agentId: data.agent_id as string,
          votedFor: data.data.voted_for as string,  // A, B, or C
          weight: data.data.weight as number,
          pieceType: data.data.piece_type as string,
          pieceSquare: data.data.piece_square as string,
          reasoning: data.data.reasoning as string,
          personality: data.data.personality as {
            self_preservation: number
            personal_glory: number
            team_victory: number
            aggression: number
            positional_dominance: number
            cooperation: number
          } | undefined,
        })
      }
      break

    case 'phase_started':
      if (data.data?.phase === 'synthesis') {
        deliberationStore.setPhase('synthesis')
      } else if (data.data?.phase === 'voting') {
        deliberationStore.setPhase('voting')
      }
      break

    case 'supervisor_decision':
    case 'deliberation_complete':
      if (data.data) {
        deliberationStore.setSelectedMove(
          data.data.selected_move as string,
          data.data.winning_choice as string || '',
          data.data.reasoning as string || ''
        )
      }
      // In the ROS flow, no subsequent agent_move event arrives (the move
      // goes back to chess_manager via ROS), so clear the thinking state here.
      // This is idempotent — safe when agent_move also calls it later.
      gameStore.setAgentThinking(false)
      break

    case 'agent_move':
      if (data.data) {
        const newFen = data.data.fen as string
        // Derive turn from FEN (second field after first space: 'w' or 'b')
        const newTurn = newFen.split(' ')[1] === 'w' ? 'white' : 'black'
        // The color that just moved is the opposite of whose turn it is now
        const movedColor = newTurn === 'white' ? 'black' : 'white'

        gameStore.updateFromServer({
          fen: newFen,
          turn: newTurn as 'white' | 'black',
          isCheck: data.data.is_check as boolean,
          isGameOver: data.data.is_game_over as boolean,
          result: data.data.result as string | null,
        })
        gameStore.setAgentThinking(false)
        gameStore.addMove({
          moveNumber: gameStore.moves.length + 1,
          color: movedColor,
          move: data.data.move as string,
          san: data.data.san as string || data.data.move as string,
          timestamp: new Date().toISOString(),
        })
      }
      break

    case 'move_made':
    case 'opponent_move':
      if (data.fen) {
        const newFen = data.fen as string
        // Derive turn from FEN (the second field after the first space)
        const turn = newFen.split(' ')[1] === 'w' ? 'white' : 'black'
        gameStore.updateFromServer({
          fen: newFen,
          turn: turn as 'white' | 'black',
          isCheck: data.is_check as boolean,
          isGameOver: data.is_game_over as boolean,
          result: data.result as string | null,
        })
        // Add the move to history
        if (data.san || data.move) {
          gameStore.addMove({
            moveNumber: gameStore.moves.length + 1,
            color: turn === 'white' ? 'black' : 'white', // The color that just moved
            move: data.move as string,
            san: (data.san || data.move) as string,
            timestamp: new Date().toISOString(),
          })
        }

        // Auto-trigger agent move if it's now the agent's turn
        const { whitePlayer, blackPlayer, gameId, isGameOver } = gameStore
        const isAgentTurn =
          (turn === 'white' && whitePlayer === 'agent') ||
          (turn === 'black' && blackPlayer === 'agent')

        if (isAgentTurn && !isGameOver && gameId) {
          // Small delay to let the UI update first
          setTimeout(() => {
            useWebSocket.getState().requestAgentMove(gameId)
          }, 300)
        }
      }
      break

    case 'game_state':
      gameStore.updateFromServer({
        fen: data.fen as string,
        turn: data.current_turn as 'white' | 'black',
        isGameOver: data.is_game_over as boolean,
        result: data.result as string | null,
        isCheck: data.is_check as boolean,
      })

      // Auto-trigger agent move if it's the agent's turn when game loads
      {
        const turn = data.current_turn as 'white' | 'black'
        const { whitePlayer, blackPlayer, gameId } = gameStore
        const isAgentTurn =
          (turn === 'white' && whitePlayer === 'agent') ||
          (turn === 'black' && blackPlayer === 'agent')
        const isGameOver = data.is_game_over as boolean

        if (isAgentTurn && !isGameOver && gameId && !gameStore.isAgentThinking) {
          setTimeout(() => {
            useWebSocket.getState().requestAgentMove(gameId)
          }, 500)
        }
      }
      break

    case 'error':
      gameStore.setError(data.message as string)
      gameStore.setAgentThinking(false)
      externalStore.handleRealTurnComplete()
      break

    // External service events
    case 'detection_started':
      externalStore.handleDetectionStarted()
      externalStore.handleRealTurnStarted()
      break

    case 'detection_complete':
      externalStore.handleDetectionComplete(data.data as {
        success: boolean
        fen?: string
        pieces?: Record<string, string>
        error?: string
      })
      // Update board if detection was successful
      if (data.data?.success && data.data?.fen) {
        gameStore.updateFromServer({
          fen: data.data.fen as string,
        })
      }
      break

    case 'robot_executing':
      externalStore.handleRobotExecuting(data.data as { move: string; san?: string })
      break

    case 'robot_complete':
      externalStore.handleRobotComplete(data.data as {
        success: boolean
        error?: string
        move: string
        san?: string
      })
      externalStore.handleRealTurnComplete()
      break

    default:
      console.log('Unknown message type:', data.type)
  }
}
