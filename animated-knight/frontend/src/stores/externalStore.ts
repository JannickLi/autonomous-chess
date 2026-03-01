import { create } from 'zustand'
import * as api from '../services/api'

export type OperationMode = 'simulation' | 'ros'

interface ExternalServiceStatus {
  type: 'mock' | 'ros'
  healthy: boolean
}

interface ExternalState {
  // Operation mode
  operationMode: OperationMode

  // Service status
  detectionStatus: ExternalServiceStatus | null
  robotStatus: ExternalServiceStatus | null

  // Operation states
  isDetecting: boolean
  isRobotExecuting: boolean
  isRealTurnInProgress: boolean

  // Detection results
  lastDetectedFen: string | null
  lastDetectedPieces: Record<string, string> | null

  // Errors
  error: string | null
  detectionError: string | null
  robotError: string | null

  // Actions
  setMode: (mode: OperationMode) => Promise<void>
  loadStatus: () => Promise<void>
  requestDetection: (gameId: string) => Promise<void>

  // Event handlers (called from WebSocket)
  handleDetectionStarted: () => void
  handleDetectionComplete: (data: { success: boolean; fen?: string; pieces?: Record<string, string>; error?: string }) => void
  handleRobotExecuting: (data: { move: string; san?: string }) => void
  handleRobotComplete: (data: { success: boolean; error?: string; move: string; san?: string }) => void
  handleRealTurnStarted: () => void
  handleRealTurnComplete: () => void

  // State management
  setError: (error: string | null) => void
  reset: () => void
}

const initialState = {
  operationMode: 'simulation' as OperationMode,
  detectionStatus: null,
  robotStatus: null,
  isDetecting: false,
  isRobotExecuting: false,
  isRealTurnInProgress: false,
  lastDetectedFen: null,
  lastDetectedPieces: null,
  error: null,
  detectionError: null,
  robotError: null,
}

export const useExternalStore = create<ExternalState>((set, get) => ({
  ...initialState,

  setMode: async (mode: OperationMode) => {
    set({ error: null })
    try {
      const result = await api.setOperationMode(mode)
      set({
        operationMode: result.mode,
      })
      // Refresh status after mode change
      await get().loadStatus()
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to set operation mode'
      set({ error: message })
      throw err
    }
  },

  loadStatus: async () => {
    try {
      const status = await api.getExternalStatus()
      set({
        operationMode: status.operation_mode,
        detectionStatus: status.detection,
        robotStatus: status.robot,
      })
    } catch (err) {
      console.error('Failed to load external status:', err)
    }
  },

  requestDetection: async (gameId: string) => {
    set({ isDetecting: true, detectionError: null })
    try {
      const result = await api.requestDetection(gameId)
      set({
        isDetecting: false,
        lastDetectedFen: result.fen,
        lastDetectedPieces: result.pieces,
        detectionError: result.error,
      })
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Detection failed'
      set({
        isDetecting: false,
        detectionError: message,
      })
      throw err
    }
  },

  // WebSocket event handlers
  handleDetectionStarted: () => {
    set({
      isDetecting: true,
      detectionError: null,
    })
  },

  handleDetectionComplete: (data) => {
    set({
      isDetecting: false,
      lastDetectedFen: data.fen || null,
      lastDetectedPieces: data.pieces || null,
      detectionError: data.error || null,
    })
  },

  handleRobotExecuting: (_data) => {
    set({
      isRobotExecuting: true,
      robotError: null,
    })
  },

  handleRobotComplete: (data) => {
    set({
      isRobotExecuting: false,
      robotError: data.error || null,
    })
  },

  handleRealTurnStarted: () => {
    set({
      isRealTurnInProgress: true,
      error: null,
      detectionError: null,
      robotError: null,
    })
  },

  handleRealTurnComplete: () => {
    set({
      isRealTurnInProgress: false,
    })
  },

  setError: (error) => {
    set({ error })
  },

  reset: () => {
    set(initialState)
  },
}))
