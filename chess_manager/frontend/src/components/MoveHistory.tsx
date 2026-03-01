import { useGameStore } from '../stores/gameStore'

export function MoveHistory() {
  const { moveHistory } = useGameStore()

  if (moveHistory.length === 0) {
    return (
      <div className="bg-slate-800 rounded-lg p-4">
        <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-3">
          Move History
        </h2>
        <p className="text-sm text-slate-500 italic">No moves yet</p>
      </div>
    )
  }

  // Pair moves into (white, black) rows
  const rows: { num: number; white: string; black?: string }[] = []
  for (let i = 0; i < moveHistory.length; i += 2) {
    rows.push({
      num: Math.floor(i / 2) + 1,
      white: moveHistory[i],
      black: moveHistory[i + 1],
    })
  }

  return (
    <div className="bg-slate-800 rounded-lg p-4">
      <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-3">
        Move History
      </h2>
      <div className="max-h-48 overflow-y-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-slate-500 text-xs">
              <th className="text-left w-8">#</th>
              <th className="text-left">White</th>
              <th className="text-left">Black</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.num} className="border-t border-slate-700/50">
                <td className="text-slate-500 py-1">{row.num}.</td>
                <td className="text-white py-1 font-mono">{row.white}</td>
                <td className="text-white py-1 font-mono">{row.black ?? ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
