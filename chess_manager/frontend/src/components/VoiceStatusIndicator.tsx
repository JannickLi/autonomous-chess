import { useGameStore } from '../stores/gameStore'

const statusConfig = {
  disabled: { label: 'Disabled', color: 'bg-slate-500', pulse: false },
  idle: { label: 'Idle', color: 'bg-slate-500', pulse: false },
  listening: { label: 'Listening', color: 'bg-blue-400', pulse: true },
  processing: { label: 'Processing', color: 'bg-amber-400', pulse: true },
}

export function VoiceStatusIndicator() {
  const { sttStatus } = useGameStore()

  const config = statusConfig[sttStatus]

  return (
    <div className="bg-slate-800 rounded-lg p-4">
      <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-3">
        Voice Input
      </h2>
      <div className="flex items-center gap-2">
        <span
          className={`w-2.5 h-2.5 rounded-full ${config.color} ${config.pulse ? 'animate-pulse' : ''}`}
        />
        <span className="text-sm text-slate-300">{config.label}</span>
      </div>
    </div>
  )
}
