/**
 * Zustand store for Chess Manager game state.
 */

import { create } from 'zustand'

export type GameStateValue =
  | 'waiting'
  | 'human_turn'
  | 'validating'
  | 'agent_turn'
  | 'thinking'
  | 'executing'
  | 'game_over'

export interface AgentOpinion {
  piece_type: string | null
  proposed_move: string
  reasoning: string
}

export interface Deliberation {
  selected_move: string
  voting_summary: string
  opinions: AgentOpinion[]
}

export type SttStatus = 'disabled' | 'listening' | 'processing' | 'idle'
export type TtsStatus = 'speaking' | 'idle'

interface GameStore {
  // Connection
  isConnected: boolean
  isConnecting: boolean

  // Game state
  state: GameStateValue
  fen: string
  turn: 'white' | 'black'
  moveHistory: string[]
  isCheck: boolean
  isGameOver: boolean
  result: string | null
  legalMovesCount: number

  // Agent deliberation
  deliberation: Deliberation | null

  // Voice status
  sttStatus: SttStatus
  ttsStatus: TtsStatus
  ttsSpeakingPiece: string | null

  // Errors
  error: string | null

  // Actions
  setConnected: (connected: boolean) => void
  setConnecting: (connecting: boolean) => void
  updateFromEvent: (data: Record<string, unknown>) => void
  setDeliberation: (data: Record<string, unknown>) => void
  setVoiceStatus: (data: Record<string, unknown>) => void
  setError: (error: string | null) => void
  reset: () => void
}

const initialState = {
  isConnected: false,
  isConnecting: false,
  state: 'waiting' as GameStateValue,
  fen: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
  turn: 'white' as const,
  moveHistory: [] as string[],
  isCheck: false,
  isGameOver: false,
  result: null as string | null,
  legalMovesCount: 20,
  deliberation: null as Deliberation | null,
  sttStatus: 'idle' as SttStatus,
  ttsStatus: 'idle' as TtsStatus,
  ttsSpeakingPiece: null as string | null,
  error: null as string | null,
}

export const useGameStore = create<GameStore>((set) => ({
  ...initialState,

  setConnected: (connected) => set({ isConnected: connected }),
  setConnecting: (connecting) => set({ isConnecting: connecting }),

  updateFromEvent: (data) =>
    set({
      state: (data.state as GameStateValue) ?? 'waiting',
      fen: (data.fen as string) ?? initialState.fen,
      turn: (data.turn as 'white' | 'black') ?? 'white',
      moveHistory: (data.move_history as string[]) ?? [],
      isCheck: (data.is_check as boolean) ?? false,
      isGameOver: (data.is_game_over as boolean) ?? false,
      result: (data.result as string | null) ?? null,
      legalMovesCount: (data.legal_moves_count as number) ?? 0,
      error: null,
    }),

  setDeliberation: (data) =>
    set({
      deliberation: {
        selected_move: (data.selected_move as string) ?? '',
        voting_summary: (data.voting_summary as string) ?? '',
        opinions: (data.opinions as AgentOpinion[]) ?? [],
      },
    }),

  setVoiceStatus: (data) => {
    const category = data.category as string
    if (category === 'tts') {
      const status = data.status as TtsStatus
      set({
        ttsStatus: status,
        ttsSpeakingPiece: status === 'speaking' ? (data.piece_type as string | null) ?? null : null,
      })
    } else if (category === 'stt') {
      set({ sttStatus: data.status as SttStatus })
    }
  },

  setError: (error) => set({ error }),

  reset: () => set(initialState),
}))
