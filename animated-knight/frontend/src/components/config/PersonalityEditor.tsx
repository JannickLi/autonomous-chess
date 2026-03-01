import { useState, useEffect, useCallback } from 'react'

interface PiecePersonality {
  self_preservation: number
  personal_glory: number
  team_victory: number
  aggression: number
  positional_dominance: number
  cooperation: number
}

interface PersonalityData {
  preset: string
  pieces: Record<string, PiecePersonality>
}

const pieceInfo = [
  { id: 'king', name: 'King', emoji: '\u265A' },
  { id: 'queen', name: 'Queen', emoji: '\u265B' },
  { id: 'rook', name: 'Rook', emoji: '\u265C' },
  { id: 'bishop', name: 'Bishop', emoji: '\u265D' },
  { id: 'knight', name: 'Knight', emoji: '\u265E' },
  { id: 'pawn', name: 'Pawn', emoji: '\u265F' },
]

const traitInfo = [
  { id: 'self_preservation', name: 'Self-Preservation', color: 'bg-green-500', description: 'Avoid being captured' },
  { id: 'personal_glory', name: 'Personal Glory', color: 'bg-yellow-500', description: 'Make impactful moves' },
  { id: 'team_victory', name: 'Team Victory', color: 'bg-blue-500', description: 'Help the team win' },
  { id: 'aggression', name: 'Aggression', color: 'bg-red-500', description: 'Attack opponents' },
  { id: 'positional_dominance', name: 'Positional', color: 'bg-purple-500', description: 'Control squares' },
  { id: 'cooperation', name: 'Cooperation', color: 'bg-cyan-500', description: 'Support teammates' },
]

const presets = [
  { id: 'default', name: 'Balanced' },
  { id: 'aggressive', name: 'Aggressive' },
  { id: 'defensive', name: 'Defensive' },
  { id: 'selfish', name: 'Selfish' },
  { id: 'teamfirst', name: 'Team First' },
]

function TraitSlider({
  trait,
  value,
  onChange,
  disabled,
}: {
  trait: typeof traitInfo[0]
  value: number
  onChange: (value: number) => void
  disabled: boolean
}) {
  return (
    <div className="flex items-center gap-2">
      <div className="w-20 text-xs text-slate-400 truncate" title={trait.description}>
        {trait.name}
      </div>
      <input
        type="range"
        min="0"
        max="100"
        value={Math.round(value * 100)}
        onChange={(e) => onChange(parseInt(e.target.value) / 100)}
        disabled={disabled}
        className="flex-1 h-1.5 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-blue-500 disabled:opacity-50"
      />
      <div className="w-8 text-xs text-slate-300 text-right">
        {Math.round(value * 100)}
      </div>
    </div>
  )
}

function PieceCard({
  piece,
  personality,
  onUpdate,
  isUpdating,
}: {
  piece: typeof pieceInfo[0]
  personality: PiecePersonality
  onUpdate: (traitId: string, value: number) => void
  isUpdating: boolean
}) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div className="bg-slate-700/50 rounded-lg overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full p-3 flex items-center justify-between hover:bg-slate-700/70 transition-colors"
      >
        <div className="flex items-center gap-2">
          <span className="text-2xl">{piece.emoji}</span>
          <span className="font-medium text-white">{piece.name}</span>
        </div>
        <span className="text-slate-400 text-sm">
          {expanded ? '\u25BC' : '\u25B6'}
        </span>
      </button>

      {expanded && (
        <div className="px-3 pb-3 space-y-2 border-t border-slate-600/50">
          {traitInfo.map((trait) => (
            <TraitSlider
              key={trait.id}
              trait={trait}
              value={personality[trait.id as keyof PiecePersonality]}
              onChange={(value) => onUpdate(trait.id, value)}
              disabled={isUpdating}
            />
          ))}
        </div>
      )}
    </div>
  )
}

export function PersonalityEditor() {
  const [data, setData] = useState<PersonalityData | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isUpdating, setIsUpdating] = useState(false)
  const [pendingUpdates, setPendingUpdates] = useState<Record<string, Record<string, number>>>({})

  const fetchData = useCallback(async () => {
    try {
      const res = await fetch('/api/games/config/personalities/details')
      const json = await res.json()
      setData(json)
    } catch (err) {
      console.error('Failed to fetch personalities:', err)
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  const handlePresetChange = async (presetId: string) => {
    setIsUpdating(true)
    try {
      await fetch(`/api/games/config/personality?preset=${presetId}`, { method: 'PUT' })
      await fetchData()
      setPendingUpdates({})
    } catch (err) {
      console.error('Failed to set preset:', err)
    } finally {
      setIsUpdating(false)
    }
  }

  const handleTraitUpdate = (pieceId: string, traitId: string, value: number) => {
    // Update local state immediately
    if (data) {
      setData({
        ...data,
        preset: 'custom',
        pieces: {
          ...data.pieces,
          [pieceId]: {
            ...data.pieces[pieceId],
            [traitId]: value,
          },
        },
      })
    }

    // Track pending updates
    setPendingUpdates((prev) => ({
      ...prev,
      [pieceId]: {
        ...(prev[pieceId] || {}),
        [traitId]: value,
      },
    }))
  }

  const applyChanges = async () => {
    setIsUpdating(true)
    try {
      for (const [pieceId, weights] of Object.entries(pendingUpdates)) {
        await fetch(`/api/games/config/personalities/${pieceId}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(weights),
        })
      }
      setPendingUpdates({})
      await fetchData()
    } catch (err) {
      console.error('Failed to apply changes:', err)
    } finally {
      setIsUpdating(false)
    }
  }

  const hasPendingChanges = Object.keys(pendingUpdates).length > 0

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-400"></div>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="text-center text-slate-400 py-8">
        Failed to load personality data
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Preset Selector */}
      <div>
        <label className="block text-sm text-slate-400 mb-2">Quick Preset</label>
        <div className="flex flex-wrap gap-2">
          {presets.map((preset) => (
            <button
              key={preset.id}
              onClick={() => handlePresetChange(preset.id)}
              disabled={isUpdating}
              className={`px-3 py-1.5 rounded text-sm transition-colors ${
                data.preset === preset.id
                  ? 'bg-purple-600 text-white'
                  : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
              } disabled:opacity-50`}
            >
              {preset.name}
            </button>
          ))}
          {data.preset === 'custom' && (
            <span className="px-3 py-1.5 rounded text-sm bg-orange-600 text-white">
              Custom
            </span>
          )}
        </div>
      </div>

      {/* Trait Legend */}
      <div className="bg-slate-700/30 rounded-lg p-3">
        <div className="text-xs text-slate-400 mb-2">Traits</div>
        <div className="grid grid-cols-2 gap-1 text-xs">
          {traitInfo.map((trait) => (
            <div key={trait.id} className="flex items-center gap-1.5">
              <div className={`w-2 h-2 rounded-full ${trait.color}`} />
              <span className="text-slate-300">{trait.name}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Piece Cards */}
      <div className="space-y-2">
        {pieceInfo.map((piece) => (
          <PieceCard
            key={piece.id}
            piece={piece}
            personality={data.pieces[piece.id]}
            onUpdate={(traitId, value) => handleTraitUpdate(piece.id, traitId, value)}
            isUpdating={isUpdating}
          />
        ))}
      </div>

      {/* Apply Button */}
      {hasPendingChanges && (
        <button
          onClick={applyChanges}
          disabled={isUpdating}
          className="w-full py-2 px-4 rounded font-medium bg-purple-600 hover:bg-purple-700 text-white transition-colors disabled:opacity-50"
        >
          {isUpdating ? 'Applying...' : 'Apply Changes'}
        </button>
      )}
    </div>
  )
}
