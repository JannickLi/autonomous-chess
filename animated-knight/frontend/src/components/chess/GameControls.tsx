import { useState, useEffect } from 'react'
import { useGameStore } from '../../stores/gameStore'

export function GameControls() {
  const {
    strategy,
    setStrategy,
    newGame,
    isAgentThinking,
    turn,
    whitePlayer,
    blackPlayer,
    isGameOver,
    supervisorModel,
    agentModel,
    availableModels,
    setSupervisorModel,
    setAgentModel,
    loadModels,
  } = useGameStore()

  // Load available models on mount
  useEffect(() => {
    loadModels()
  }, [loadModels])
  const [showNewGameModal, setShowNewGameModal] = useState(false)
  const [newGameOptions, setNewGameOptions] = useState({
    strategy: 'hybrid',
    whitePlayer: 'human',
    blackPlayer: 'agent',
  })

  const isAgentTurn =
    (turn === 'white' && whitePlayer === 'agent') ||
    (turn === 'black' && blackPlayer === 'agent')

  const handleNewGame = () => {
    newGame(newGameOptions)
    setShowNewGameModal(false)
  }

  return (
    <div className="bg-slate-800/80 backdrop-blur rounded-2xl border border-slate-700/50 p-4">
      <h3 className="text-base font-semibold text-white mb-4">Game Controls</h3>

      {/* Strategy selector */}
      <div className="mb-4">
        <label className="block text-sm text-slate-400 mb-2">Strategy</label>
        <select
          value={strategy}
          onChange={(e) => setStrategy(e.target.value)}
          className="w-full bg-slate-700/60 text-white rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 border border-slate-600/30"
          disabled={isAgentThinking}
        >
          <option value="hybrid">Democratic (Supervisor + Piece Voting)</option>
          <option value="supervisor">Supervisor Only</option>
        </select>
        <p className="text-xs text-slate-500 mt-1">
          {strategy === 'hybrid' && 'Supervisor proposes candidates, pieces vote based on personality'}
          {strategy === 'supervisor' && 'Central supervisor makes all decisions'}
        </p>
      </div>

      {/* Supervisor Model selector */}
      <div className="mb-4">
        <label className="block text-sm text-slate-400 mb-2">Supervisor Model (Analysis)</label>
        <select
          value={supervisorModel}
          onChange={(e) => setSupervisorModel(e.target.value)}
          className="w-full bg-slate-700/60 text-white rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 border border-slate-600/30"
          disabled={isAgentThinking}
        >
          {availableModels.length > 0 ? (
            availableModels.map((model) => (
              <option key={model} value={model}>
                {model}
              </option>
            ))
          ) : (
            <option value={supervisorModel}>{supervisorModel}</option>
          )}
        </select>
        <p className="text-xs text-slate-500 mt-1">
          Reasoning model for detailed position analysis
        </p>
      </div>

      {/* Agent Model selector */}
      <div className="mb-4">
        <label className="block text-sm text-slate-400 mb-2">Agent Model (Voting)</label>
        <select
          value={agentModel}
          onChange={(e) => setAgentModel(e.target.value)}
          className="w-full bg-slate-700/60 text-white rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 border border-slate-600/30"
          disabled={isAgentThinking}
        >
          {availableModels.length > 0 ? (
            availableModels.map((model) => (
              <option key={model} value={model}>
                {model}
              </option>
            ))
          ) : (
            <option value={agentModel}>{agentModel}</option>
          )}
        </select>
        <p className="text-xs text-slate-500 mt-1">
          Faster model for piece agent voting
        </p>
      </div>

      {/* Action buttons */}
      <div className="space-y-2">
        {isAgentTurn && !isGameOver && (
          <div
            className="w-full py-2 px-4 rounded font-medium bg-slate-600 text-slate-300 text-center"
          >
            {isAgentThinking ? (
              <span className="flex items-center justify-center">
                <span className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-400 mr-2"></span>
                Agent thinking...
              </span>
            ) : (
              <span className="flex items-center justify-center">
                <span className="animate-pulse mr-2">⏳</span>
                Agent's turn
              </span>
            )}
          </div>
        )}

        <button
          onClick={() => setShowNewGameModal(true)}
          className="w-full py-2 px-4 rounded font-medium bg-slate-700 hover:bg-slate-600 text-white transition-colors"
        >
          New Game
        </button>
      </div>

      {/* Game info */}
      <div className="mt-4 pt-4 border-t border-slate-700">
        <div className="text-sm text-slate-400 space-y-1">
          <div className="flex justify-between">
            <span>White:</span>
            <span className="text-white capitalize">{whitePlayer}</span>
          </div>
          <div className="flex justify-between">
            <span>Black:</span>
            <span className="text-white capitalize">{blackPlayer}</span>
          </div>
          <div className="flex justify-between">
            <span>Strategy:</span>
            <span className="text-white capitalize">{strategy}</span>
          </div>
          <div className="flex justify-between">
            <span>Supervisor:</span>
            <span className="text-white text-xs">{supervisorModel.replace('-latest', '')}</span>
          </div>
          <div className="flex justify-between">
            <span>Agents:</span>
            <span className="text-white text-xs">{agentModel.replace('-latest', '')}</span>
          </div>
        </div>
      </div>

      {/* New Game Modal */}
      {showNewGameModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-slate-800 rounded-lg p-6 w-96">
            <h3 className="text-xl font-semibold text-white mb-4">New Game</h3>

            <div className="space-y-4">
              <div>
                <label className="block text-sm text-slate-400 mb-2">Strategy</label>
                <select
                  value={newGameOptions.strategy}
                  onChange={(e) =>
                    setNewGameOptions({ ...newGameOptions, strategy: e.target.value })
                  }
                  className="w-full bg-slate-700 text-white rounded px-3 py-2"
                >
                  <option value="hybrid">Democratic (Supervisor + Piece Voting)</option>
                  <option value="supervisor">Supervisor Only</option>
                </select>
              </div>

              <div>
                <label className="block text-sm text-slate-400 mb-2">White Player</label>
                <select
                  value={newGameOptions.whitePlayer}
                  onChange={(e) =>
                    setNewGameOptions({ ...newGameOptions, whitePlayer: e.target.value })
                  }
                  className="w-full bg-slate-700 text-white rounded px-3 py-2"
                >
                  <option value="human">Human</option>
                  <option value="agent">Agent</option>
                </select>
              </div>

              <div>
                <label className="block text-sm text-slate-400 mb-2">Black Player</label>
                <select
                  value={newGameOptions.blackPlayer}
                  onChange={(e) =>
                    setNewGameOptions({ ...newGameOptions, blackPlayer: e.target.value })
                  }
                  className="w-full bg-slate-700 text-white rounded px-3 py-2"
                >
                  <option value="human">Human</option>
                  <option value="agent">Agent</option>
                </select>
              </div>
            </div>

            <div className="flex space-x-3 mt-6">
              <button
                onClick={() => setShowNewGameModal(false)}
                className="flex-1 py-2 px-4 rounded bg-slate-700 hover:bg-slate-600 text-white"
              >
                Cancel
              </button>
              <button
                onClick={handleNewGame}
                className="flex-1 py-2 px-4 rounded bg-blue-600 hover:bg-blue-700 text-white"
              >
                Start Game
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
