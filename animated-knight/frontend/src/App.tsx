import { useEffect, useState } from 'react'
import { GameControls } from './components/chess/GameControls'
import { AgentPanel } from './components/agents/AgentPanel'
import { DeliberationView } from './components/agents/DeliberationView'
import { PersonalityEditor } from './components/config/PersonalityEditor'
import { ModeControls } from './components/ModeControls'
import { NavigationBar } from './components/NavigationBar'
import { useGameStore } from './stores/gameStore'
import { useWebSocket } from './services/websocket'

type TabId = 'game' | 'personality'

function App() {
  const { gameId, initGame } = useGameStore()
  const { connect, isConnected } = useWebSocket()
  const [activeTab, setActiveTab] = useState<TabId>('game')

  useEffect(() => {
    // Initialize game on mount
    initGame()
  }, [initGame])

  useEffect(() => {
    // Connect WebSocket when game is created, then request game state
    // so the auto-trigger logic can check if it's the agent's turn
    if (gameId) {
      connect(gameId)
    }
  }, [gameId, connect])

  useEffect(() => {
    if (isConnected && gameId) {
      useWebSocket.getState().send({ type: 'get_state', game_id: gameId })
    }
  }, [isConnected, gameId])

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 to-slate-800 p-4">
      <header className="mb-6 text-center">
        <h1 className="text-3xl font-bold text-white mb-1 tracking-tight">Chess Agents</h1>
        <p className="text-slate-500 text-sm">Multi-Agent LLM Chess System</p>
        {isConnected && (
          <span className="inline-flex items-center text-xs text-green-400 mt-2">
            <span className="w-1.5 h-1.5 bg-green-400 rounded-full mr-1.5 animate-pulse"></span>
            Connected
          </span>
        )}
        <div className="mt-2">
          <NavigationBar />
        </div>
      </header>

      <main className="max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left Panel - Tabbed Controls */}
        <div className="lg:col-span-1 space-y-4">
          {/* Tab Header */}
          <div className="flex bg-slate-800/80 rounded-xl p-1 border border-slate-700/50">
            <button
              onClick={() => setActiveTab('game')}
              className={`flex-1 py-2 px-4 rounded text-sm font-medium transition-colors ${
                activeTab === 'game'
                  ? 'bg-blue-600 text-white'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              Game
            </button>
            <button
              onClick={() => setActiveTab('personality')}
              className={`flex-1 py-2 px-4 rounded text-sm font-medium transition-colors ${
                activeTab === 'personality'
                  ? 'bg-purple-600 text-white'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              Personalities
            </button>
          </div>

          {/* Tab Content */}
          {activeTab === 'game' && (
            <>
              <AgentPanel />
              <GameControls />
              <ModeControls />
            </>
          )}

          {activeTab === 'personality' && (
            <div className="bg-slate-800/80 backdrop-blur rounded-2xl border border-slate-700/50 p-4">
              <h3 className="text-base font-semibold text-white mb-4">
                Piece Personalities
              </h3>
              <p className="text-sm text-slate-400 mb-4">
                Customize how each piece evaluates and votes on moves.
                Higher values mean the piece cares more about that trait.
              </p>
              <PersonalityEditor />
            </div>
          )}
        </div>

        {/* Right Panel - Deliberation */}
        <div className="lg:col-span-1 space-y-4">
          <DeliberationView />
        </div>
      </main>
    </div>
  )
}

export default App
