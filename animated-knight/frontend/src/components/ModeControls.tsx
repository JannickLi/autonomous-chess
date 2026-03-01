import { useEffect } from 'react'
import { useExternalStore } from '../stores/externalStore'
import { useGameStore } from '../stores/gameStore'
import { useWebSocket } from '../services/websocket'

export function ModeControls() {
  const {
    operationMode,
    setMode,
    loadStatus,
    isDetecting,
    isRobotExecuting,
    isRealTurnInProgress,
    lastDetectedFen,
    detectionStatus,
    robotStatus,
    error,
    detectionError,
    robotError,
  } = useExternalStore()

  const { gameId, isAgentThinking, isGameOver } = useGameStore()
  const { requestRealTurn } = useWebSocket()

  // Load status on mount
  useEffect(() => {
    loadStatus()
  }, [loadStatus])

  const handleModeChange = async (mode: 'simulation' | 'ros') => {
    try {
      await setMode(mode)
    } catch (err) {
      console.error('Failed to change mode:', err)
    }
  }

  const handleCaptureBoard = () => {
    if (gameId && !isRealTurnInProgress && !isAgentThinking) {
      requestRealTurn(gameId)
    }
  }

  const isWorking = isDetecting || isRobotExecuting || isRealTurnInProgress || isAgentThinking
  const canCapture = gameId && !isWorking && !isGameOver

  return (
    <div className="bg-slate-800 rounded-lg p-4">
      <h3 className="text-lg font-semibold text-white mb-4">Operation Mode</h3>

      {/* Mode Toggle */}
      <div className="flex rounded-lg overflow-hidden mb-4">
        <button
          onClick={() => handleModeChange('simulation')}
          disabled={isWorking}
          className={`flex-1 py-2 px-4 text-sm font-medium transition-colors ${
            operationMode === 'simulation'
              ? 'bg-blue-600 text-white'
              : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
          } ${isWorking ? 'opacity-50 cursor-not-allowed' : ''}`}
        >
          Simulation
        </button>
        <button
          onClick={() => handleModeChange('ros')}
          disabled={isWorking}
          className={`flex-1 py-2 px-4 text-sm font-medium transition-colors ${
            operationMode === 'ros'
              ? 'bg-green-600 text-white'
              : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
          } ${isWorking ? 'opacity-50 cursor-not-allowed' : ''}`}
        >
          ROS
        </button>
      </div>

      {/* Mode description */}
      <p className="text-xs text-slate-500 mb-4">
        {operationMode === 'simulation'
          ? 'Web-only chess - moves are displayed on screen'
          : 'Camera detects board state, robot executes moves'}
      </p>

      {/* Capture Board Button (Real mode) */}
      {operationMode === 'ros' && (
        <button
          onClick={handleCaptureBoard}
          disabled={!canCapture}
          className={`w-full py-3 px-4 rounded-lg font-medium transition-colors mb-4 ${
            canCapture
              ? 'bg-green-600 hover:bg-green-700 text-white'
              : 'bg-slate-700 text-slate-500 cursor-not-allowed'
          }`}
        >
          {isDetecting ? (
            <span className="flex items-center justify-center">
              <span className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></span>
              Detecting board...
            </span>
          ) : isAgentThinking ? (
            <span className="flex items-center justify-center">
              <span className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></span>
              Agent thinking...
            </span>
          ) : isRobotExecuting ? (
            <span className="flex items-center justify-center">
              <span className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></span>
              Robot executing...
            </span>
          ) : (
            'Capture Board'
          )}
        </button>
      )}

      {/* Status indicators */}
      {operationMode === 'ros' && (
        <div className="space-y-2 mb-4">
          <div className="flex items-center justify-between text-sm">
            <span className="text-slate-400">Detection:</span>
            <StatusBadge
              status={isDetecting ? 'working' : detectionStatus?.healthy ? 'ready' : 'offline'}
              label={isDetecting ? 'Capturing' : detectionStatus?.healthy ? 'Ready' : 'Offline'}
            />
          </div>
          <div className="flex items-center justify-between text-sm">
            <span className="text-slate-400">Robot:</span>
            <StatusBadge
              status={isRobotExecuting ? 'working' : robotStatus?.healthy ? 'ready' : 'offline'}
              label={isRobotExecuting ? 'Executing' : robotStatus?.healthy ? 'Ready' : 'Offline'}
            />
          </div>
        </div>
      )}

      {/* Last detected FEN */}
      {operationMode === 'ros' && lastDetectedFen && (
        <div className="mb-4">
          <span className="text-xs text-slate-500 block mb-1">Last detected:</span>
          <code className="text-xs text-slate-400 bg-slate-900 px-2 py-1 rounded block overflow-x-auto">
            {lastDetectedFen.split(' ')[0]}
          </code>
        </div>
      )}

      {/* Error display */}
      {(error || detectionError || robotError) && (
        <div className="bg-red-900/30 border border-red-700 rounded p-3 mb-4">
          <span className="text-red-400 text-sm">
            {error || detectionError || robotError}
          </span>
        </div>
      )}

      {/* Service info */}
      {operationMode === 'ros' && (
        <div className="text-xs text-slate-500 space-y-1">
          <div className="flex justify-between">
            <span>Detection:</span>
            <span className={detectionStatus?.type === 'ros' ? 'text-green-400' : 'text-yellow-400'}>
              {detectionStatus?.type || 'unknown'}
            </span>
          </div>
          <div className="flex justify-between">
            <span>Robot:</span>
            <span className={robotStatus?.type === 'ros' ? 'text-green-400' : 'text-yellow-400'}>
              {robotStatus?.type || 'unknown'}
            </span>
          </div>
        </div>
      )}
    </div>
  )
}

interface StatusBadgeProps {
  status: 'ready' | 'working' | 'offline'
  label: string
}

function StatusBadge({ status, label }: StatusBadgeProps) {
  const colors = {
    ready: 'bg-green-900/50 text-green-400 border-green-700',
    working: 'bg-blue-900/50 text-blue-400 border-blue-700',
    offline: 'bg-slate-700 text-slate-500 border-slate-600',
  }

  const dots = {
    ready: 'bg-green-400',
    working: 'bg-blue-400 animate-pulse',
    offline: 'bg-slate-500',
  }

  return (
    <span className={`px-2 py-0.5 rounded text-xs border flex items-center ${colors[status]}`}>
      <span className={`w-1.5 h-1.5 rounded-full mr-1.5 ${dots[status]}`}></span>
      {label}
    </span>
  )
}
