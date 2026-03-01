import { useEffect } from 'react'
import { ChessBoard } from './components/ChessBoard'
import { StateIndicator } from './components/StateIndicator'
import { GameControls } from './components/GameControls'
import { MoveHistory } from './components/MoveHistory'
import { DeliberationPanel } from './components/DeliberationPanel'
import { FenDisplay } from './components/FenDisplay'
import { ConnectionStatus } from './components/ConnectionStatus'
import { VoiceStatusIndicator } from './components/VoiceStatusIndicator'
import { NavigationBar } from './components/NavigationBar'
import { connect, disconnect } from './services/websocket'

function App() {
  useEffect(() => {
    connect()
    return () => disconnect()
  }, [])

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 to-slate-800 p-4">
      <header className="mb-6 text-center">
        <h1 className="text-3xl font-bold text-white mb-2">Chess Manager</h1>
        <p className="text-slate-400">Game Orchestration Dashboard</p>
        <div className="mt-2 flex flex-col items-center gap-2">
          <ConnectionStatus />
          <NavigationBar />
        </div>
      </header>

      <main className="max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Panel - State & Controls */}
        <div className="lg:col-span-1 space-y-4">
          <StateIndicator />
          <VoiceStatusIndicator />
          <GameControls />
          <FenDisplay />
        </div>

        {/* Center - Chess Board */}
        <div className="lg:col-span-1 flex justify-center">
          <ChessBoard />
        </div>

        {/* Right Panel - Deliberation & History */}
        <div className="lg:col-span-1 space-y-4">
          <DeliberationPanel />
          <MoveHistory />
        </div>
      </main>
    </div>
  )
}

export default App
