import { useGameStore } from '../../stores/gameStore'

export function MoveHistory() {
  const { moves } = useGameStore()

  // Group moves into pairs (white, black)
  const movePairs: Array<{ number: number; white?: string; black?: string }> = []
  for (let i = 0; i < moves.length; i += 2) {
    movePairs.push({
      number: Math.floor(i / 2) + 1,
      white: moves[i]?.san,
      black: moves[i + 1]?.san,
    })
  }

  return (
    <div className="bg-slate-800/80 backdrop-blur rounded-2xl border border-slate-700/50 p-4">
      <div className="flex items-center gap-2 mb-3">
        <div className="w-2 h-2 rounded-full bg-slate-500" />
        <h3 className="text-base font-semibold text-white">Move History</h3>
        {moves.length > 0 && (
          <span className="text-[10px] px-1.5 py-0.5 bg-slate-700/50 text-slate-500 rounded-full">
            {moves.length}
          </span>
        )}
      </div>

      {moves.length === 0 ? (
        <p className="text-slate-500 text-sm text-center py-4">No moves yet</p>
      ) : (
        <div className="max-h-48 overflow-y-auto custom-scrollbar">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-slate-500 border-b border-slate-700/50">
                <th className="pb-2 text-left w-10 text-xs font-medium">#</th>
                <th className="pb-2 text-left text-xs font-medium">White</th>
                <th className="pb-2 text-left text-xs font-medium">Black</th>
              </tr>
            </thead>
            <tbody>
              {movePairs.map((pair) => (
                <tr key={pair.number} className="border-b border-slate-700/20">
                  <td className="py-1.5 text-slate-600 text-xs">{pair.number}.</td>
                  <td className="py-1.5 text-white font-mono text-sm">{pair.white || ''}</td>
                  <td className="py-1.5 text-slate-400 font-mono text-sm">{pair.black || ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
