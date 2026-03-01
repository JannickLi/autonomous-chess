import { useGameStore } from '../stores/gameStore'

export function ConnectionStatus() {
  const { isConnected, isConnecting } = useGameStore()

  if (isConnecting) {
    return (
      <span className="inline-flex items-center text-xs text-yellow-400">
        <span className="w-2 h-2 bg-yellow-400 rounded-full mr-2 animate-pulse" />
        Connecting...
      </span>
    )
  }

  if (isConnected) {
    return (
      <span className="inline-flex items-center text-xs text-green-400">
        <span className="w-2 h-2 bg-green-400 rounded-full mr-2 animate-pulse" />
        Connected
      </span>
    )
  }

  return (
    <span className="inline-flex items-center text-xs text-red-400">
      <span className="w-2 h-2 bg-red-400 rounded-full mr-2" />
      Disconnected
    </span>
  )
}
