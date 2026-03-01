import { useGameStore } from '../stores/gameStore'

export function FenDisplay() {
  const { fen } = useGameStore()

  return (
    <div className="bg-slate-800 rounded-lg p-4">
      <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-2">
        Position (FEN)
      </h2>
      <code className="text-xs text-slate-300 font-mono break-all block bg-slate-900 rounded px-2 py-1.5">
        {fen}
      </code>
    </div>
  )
}
