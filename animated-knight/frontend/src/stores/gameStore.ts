import { create } from 'zustand'
import { Chess } from 'chess.js'
import * as api from '../services/api'

export interface MoveRecord {
  moveNumber: number
  color: 'white' | 'black'
  move: string
  san: string
  timestamp: string
}

interface GameState {
  // Game state
  gameId: string | null
  fen: string
  turn: 'white' | 'black'
  isGameOver: boolean
  result: string | null
  isCheck: boolean
  strategy: string
  whitePlayer: 'human' | 'agent'
  blackPlayer: 'human' | 'agent'

  // LLM config (separate models for supervisor and agents)
  supervisorModel: string
  agentModel: string
  availableModels: string[]

  // Move history
  moves: MoveRecord[]

  // UI state
  isLoading: boolean
  isAgentThinking: boolean
  error: string | null

  // Actions
  initGame: () => Promise<void>
  makeMove: (from: string, to: string, promotion?: string) => Promise<boolean>
  requestAgentMove: () => Promise<void>
  setStrategy: (strategy: string) => Promise<void>
  setSupervisorModel: (model: string) => Promise<void>
  setAgentModel: (model: string) => Promise<void>
  loadModels: () => Promise<void>
  newGame: (options?: { strategy?: string; whitePlayer?: string; blackPlayer?: string }) => Promise<void>
  updateFromServer: (data: Partial<GameState>) => void
  addMove: (move: MoveRecord) => void
  setAgentThinking: (thinking: boolean) => void
  setError: (error: string | null) => void
}

export const useGameStore = create<GameState>((set, get) => ({
  // Initial state
  gameId: null,
  fen: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
  turn: 'white',
  isGameOver: false,
  result: null,
  isCheck: false,
  strategy: 'hybrid',
  whitePlayer: 'human',
  blackPlayer: 'agent',
  supervisorModel: 'mistral-medium-latest',
  agentModel: 'mistral-small-latest',
  availableModels: [],
  moves: [],
  isLoading: false,
  isAgentThinking: false,
  error: null,

  initGame: async () => {
    set({ isLoading: true, error: null })
    try {
      const game = await api.createGame({
        strategy: get().strategy,
        whitePlayer: get().whitePlayer,
        blackPlayer: get().blackPlayer,
      })
      set({
        gameId: game.id,
        fen: game.fen,
        turn: game.current_turn as 'white' | 'black',
        strategy: game.strategy,
        whitePlayer: game.white_player as 'human' | 'agent',
        blackPlayer: game.black_player as 'human' | 'agent',
        moves: [],
        isGameOver: false,
        result: null,
        isLoading: false,
      })
    } catch (err) {
      set({ error: 'Failed to create game', isLoading: false })
    }
  },

  makeMove: async (from: string, to: string, promotion?: string) => {
    const { gameId, fen } = get()
    if (!gameId) return false

    // Validate move locally first
    const chess = new Chess(fen)
    const move = chess.move({ from, to, promotion })
    if (!move) return false

    set({ isLoading: true, error: null })
    try {
      const result = await api.makeMove(gameId, `${from}${to}${promotion || ''}`)

      set({
        fen: result.fen,
        turn: chess.turn() === 'w' ? 'white' : 'black',
        isCheck: result.is_check,
        isGameOver: result.is_game_over,
        result: result.result,
        isLoading: false,
      })

      // Add move to history
      get().addMove({
        moveNumber: get().moves.length + 1,
        color: move.color === 'w' ? 'white' : 'black',
        move: `${from}${to}${promotion || ''}`,
        san: move.san,
        timestamp: new Date().toISOString(),
      })

      return true
    } catch (err) {
      set({ error: 'Failed to make move', isLoading: false })
      return false
    }
  },

  requestAgentMove: async () => {
    const { gameId } = get()
    if (!gameId) return

    set({ isAgentThinking: true, error: null })
    try {
      const result = await api.requestAgentMove(gameId)

      set({
        fen: result.fen,
        turn: result.fen.includes(' w ') ? 'white' : 'black',
        isCheck: result.is_check,
        isGameOver: result.is_game_over,
        result: result.result,
        isAgentThinking: false,
      })

      // Add move to history
      get().addMove({
        moveNumber: get().moves.length + 1,
        color: get().turn === 'white' ? 'black' : 'white',
        move: result.move,
        san: result.move, // API should return SAN
        timestamp: new Date().toISOString(),
      })
    } catch (err) {
      set({ error: 'Failed to get agent move', isAgentThinking: false })
    }
  },

  setStrategy: async (strategy: string) => {
    const { gameId } = get()
    set({ strategy })

    // Sync with backend if game exists
    if (gameId) {
      try {
        await fetch(`/api/games/${gameId}/strategy?strategy=${strategy}`, {
          method: 'PUT',
        })
      } catch (err) {
        console.error('Failed to update strategy on server:', err)
      }
    }
  },

  setSupervisorModel: async (model: string) => {
    try {
      await api.setSupervisorModel(model)
      set({ supervisorModel: model })
    } catch (err) {
      console.error('Failed to set supervisor model:', err)
      set({ error: 'Failed to set supervisor model' })
    }
  },

  setAgentModel: async (model: string) => {
    try {
      await api.setAgentModel(model)
      set({ agentModel: model })
    } catch (err) {
      console.error('Failed to set agent model:', err)
      set({ error: 'Failed to set agent model' })
    }
  },

  loadModels: async () => {
    try {
      const { supervisor_model, agent_model, available } = await api.getModels()
      set({ supervisorModel: supervisor_model, agentModel: agent_model, availableModels: available })
    } catch (err) {
      console.error('Failed to load models:', err)
    }
  },

  newGame: async (options) => {
    set({
      strategy: options?.strategy || get().strategy,
      whitePlayer: (options?.whitePlayer as 'human' | 'agent') || get().whitePlayer,
      blackPlayer: (options?.blackPlayer as 'human' | 'agent') || get().blackPlayer,
    })
    await get().initGame()
  },

  updateFromServer: (data) => {
    set((state) => ({
      ...state,
      ...data,
    }))
  },

  addMove: (move) => {
    set((state) => ({
      moves: [...state.moves, move],
    }))
  },

  setAgentThinking: (thinking) => {
    set({ isAgentThinking: thinking })
  },

  setError: (error) => {
    set({ error })
  },
}))
