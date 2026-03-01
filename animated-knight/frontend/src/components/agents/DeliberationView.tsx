import { useState } from 'react'
import { useDeliberationStore, Personality } from '../../stores/deliberationStore'
import { useGameStore } from '../../stores/gameStore'
import { PieceAvatar } from './PieceAvatar'

const pieceEmojis: Record<string, string> = {
  king: '\u265A',
  queen: '\u265B',
  rook: '\u265C',
  bishop: '\u265D',
  knight: '\u265E',
  pawn: '\u265F',
}

function PersonalityMiniBar({ personality }: { personality: Personality }) {
  const traits = [
    { key: 'self_preservation', color: 'bg-green-500', label: 'Self-Pres' },
    { key: 'personal_glory', color: 'bg-yellow-500', label: 'Glory' },
    { key: 'team_victory', color: 'bg-blue-500', label: 'Team' },
    { key: 'aggression', color: 'bg-red-500', label: 'Aggr' },
    { key: 'positional_dominance', color: 'bg-purple-500', label: 'Pos' },
    { key: 'cooperation', color: 'bg-cyan-500', label: 'Coop' },
  ]

  return (
    <div className="flex gap-0.5 items-end" title="Personality traits">
      {traits.map((trait) => {
        const value = personality[trait.key as keyof Personality]
        const height = Math.max(3, Math.round(value * 12))
        return (
          <div
            key={trait.key}
            className={`w-1.5 rounded-sm ${trait.color} opacity-80`}
            style={{ height: `${height}px` }}
            title={`${trait.label}: ${Math.round(value * 100)}%`}
          />
        )
      })}
    </div>
  )
}

export function DeliberationView() {
  const {
    isDeliberating,
    currentPhase,
    proposals,
    votes,
    voteSummary,
    selectedMove,
    winningChoice,
    reasoning,
  } = useDeliberationStore()

  const { isAgentThinking, turn } = useGameStore()
  const [selectedProposalIdx, setSelectedProposalIdx] = useState<number | null>(null)
  const [expandedVoteIdx, setExpandedVoteIdx] = useState<number | null>(null)

  const phaseConfig: Record<string, { label: string; color: string; bgColor: string }> = {
    idle: { label: 'Waiting', color: 'text-slate-400', bgColor: 'bg-slate-500/20' },
    proposing: { label: 'Gathering Proposals', color: 'text-amber-400', bgColor: 'bg-amber-500/20' },
    voting: { label: 'Voting', color: 'text-blue-400', bgColor: 'bg-blue-500/20' },
    synthesis: { label: 'Synthesizing', color: 'text-purple-400', bgColor: 'bg-purple-500/20' },
    complete: { label: 'Complete', color: 'text-green-400', bgColor: 'bg-green-500/20' },
  }

  const phase = phaseConfig[currentPhase] || phaseConfig.idle

  const selectedProposal = selectedProposalIdx !== null ? proposals[selectedProposalIdx] : null

  const pieceColor = turn as 'white' | 'black'

  return (
    <div className="bg-slate-800/80 backdrop-blur rounded-2xl border border-slate-700/50 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-slate-700/50">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-blue-500" />
          <h3 className="text-base font-semibold text-white">Deliberation</h3>
        </div>
        {(isDeliberating || isAgentThinking) && (
          <span className={`text-xs px-3 py-1 ${phase.bgColor} ${phase.color} rounded-full animate-pulse font-medium`}>
            {phase.label}
          </span>
        )}
        {!isDeliberating && !isAgentThinking && currentPhase === 'complete' && (
          <span className={`text-xs px-3 py-1 ${phase.bgColor} ${phase.color} rounded-full font-medium`}>
            {phase.label}
          </span>
        )}
      </div>

      <div className="p-4">
        {!isDeliberating && !isAgentThinking && proposals.length === 0 ? (
          <div className="text-center py-8">
            <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-slate-700/50 mb-3">
              <span className="text-3xl opacity-50">{'\u265E'}</span>
            </div>
            <p className="text-slate-500 text-sm">
              Agent deliberation will appear here
            </p>
            <p className="text-slate-600 text-xs mt-1">
              Start a new game with an agent player to see deliberation
            </p>
          </div>
        ) : (
          <div className="space-y-5">

            {/* Strategic Options — border-l-4 accent style */}
            {proposals.length > 0 && (
              <div>
                <SectionHeader title="Strategic Options" count={proposals.length} />
                <div className="space-y-2 mt-2">
                  {proposals.map((proposal, idx) => {
                    const choice = proposal.choice || ['A', 'B', 'C'][idx]
                    const isWinner = winningChoice === choice
                    const isSelected = selectedProposalIdx === idx
                    return (
                      <div key={`${proposal.agentId}-${idx}`}>
                        <div
                          onClick={() => setSelectedProposalIdx(isSelected ? null : idx)}
                          className={`border-l-4 pl-3 pr-3 py-2.5 cursor-pointer transition-all duration-200 rounded-r-lg
                            ${isWinner
                              ? 'border-green-500 bg-green-500/10'
                              : 'border-slate-600 hover:border-slate-500 hover:bg-slate-700/30'}
                            ${isSelected ? 'bg-slate-700/40' : ''}
                          `}
                        >
                          <div className="flex items-center gap-2 mb-0.5">
                            <span className={`font-bold text-sm ${isWinner ? 'text-green-400' : 'text-blue-400'}`}>
                              Option {choice}
                            </span>
                            {isWinner && (
                              <span className="text-[10px] px-2 py-0.5 bg-green-500/20 text-green-400 rounded-full uppercase tracking-wider font-semibold">
                                Winner
                              </span>
                            )}
                          </div>
                          <p className="text-sm text-slate-300 leading-relaxed">{proposal.description}</p>
                        </div>

                        {/* Expanded proposal details */}
                        {isSelected && selectedProposal && (
                          <div className="ml-4 mt-1 p-3 bg-slate-700/40 rounded-lg border-l-2 border-slate-600/50">
                            <p className="text-sm text-slate-200 leading-relaxed mb-2">{selectedProposal.reasoning}</p>
                            {selectedProposal.pieceImpacts && Object.keys(selectedProposal.pieceImpacts).length > 0 && (
                              <div>
                                <div className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold mb-1.5">
                                  Impact on Pieces
                                </div>
                                <div className="space-y-1">
                                  {Object.entries(selectedProposal.pieceImpacts).map(([piece, impact]) => {
                                    const pType = piece.split('_')[0]
                                    return (
                                      <div key={piece} className="flex items-center gap-2 text-xs">
                                        <PieceAvatar pieceType={pType} color={pieceColor} size="sm" />
                                        <span className="text-slate-400 capitalize font-medium">{piece.replace('_', ' ')}:</span>
                                        <span className="text-slate-300">{impact}</span>
                                      </div>
                                    )
                                  })}
                                </div>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>
            )}

            {/* Votes — table layout */}
            {votes.length > 0 && (
              <div>
                <SectionHeader
                  title="Votes"
                  count={votes.length}
                  subtitle="Click a row to see reasoning"
                />
                <div className="mt-2 max-h-[400px] overflow-y-auto custom-scrollbar">
                  <table className="w-full">
                    <thead>
                      <tr className="text-[10px] text-slate-500 uppercase tracking-wider">
                        <th className="text-left pb-2 font-semibold">Piece</th>
                        <th className="text-center pb-2 font-semibold w-14">Vote</th>
                        <th className="text-right pb-2 font-semibold w-14">Weight</th>
                      </tr>
                    </thead>
                    <tbody>
                      {votes.map((vote, idx) => {
                        const isWinnerVote = vote.votedFor === winningChoice
                        const pieceType = vote.pieceType || vote.agentId.split('_')[0]
                        const isExpanded = expandedVoteIdx === idx
                        const emoji = pieceEmojis[pieceType.toLowerCase()] || '\u265F'
                        return (
                          <VoteRow
                            key={`${vote.agentId}-${idx}`}
                            emoji={emoji}
                            pieceType={pieceType}
                            square={vote.pieceSquare}
                            personality={vote.personality}
                            votedFor={vote.votedFor}
                            weight={vote.weight || 1}
                            isWinnerVote={isWinnerVote}
                            isExpanded={isExpanded}
                            reasoning={vote.reasoning}
                            onToggle={() => setExpandedVoteIdx(isExpanded ? null : idx)}
                            index={idx}
                          />
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* Vote Tally */}
            {Object.keys(voteSummary).length > 0 && (
              <div>
                <SectionHeader title="Vote Tally" />
                <div className="space-y-2 mt-2">
                  {Object.entries(voteSummary)
                    .sort(([, a], [, b]) => b - a)
                    .map(([choice, score]) => {
                      const maxScore = Math.max(...Object.values(voteSummary))
                      const totalScore = Object.values(voteSummary).reduce((a, b) => a + b, 0)
                      const percentage = (score / maxScore) * 100
                      const sharePercent = totalScore > 0 ? Math.round((score / totalScore) * 100) : 0
                      const isWinner = choice === winningChoice
                      return (
                        <div key={choice} className="relative overflow-hidden rounded-lg">
                          {/* Background bar */}
                          <div
                            className={`absolute inset-y-0 left-0 rounded-lg transition-all duration-700 ease-out ${
                              isWinner ? 'bg-green-500/20' : 'bg-blue-500/10'
                            }`}
                            style={{ width: `${percentage}%` }}
                          />
                          <div className="relative flex items-center justify-between py-2.5 px-3">
                            <div className="flex items-center gap-2">
                              <span
                                className={`font-bold text-sm w-6 h-6 rounded flex items-center justify-center ${
                                  isWinner
                                    ? 'bg-green-500/20 text-green-400'
                                    : 'bg-slate-600/40 text-slate-300'
                                }`}
                              >
                                {choice}
                              </span>
                              {isWinner && (
                                <span className="text-green-400 text-sm">{'\u2713'}</span>
                              )}
                            </div>
                            <div className="flex items-center gap-3">
                              <span className="text-xs text-slate-500">{sharePercent}%</span>
                              <span className={`text-sm font-semibold ${isWinner ? 'text-green-400' : 'text-slate-300'}`}>
                                {score.toFixed(1)} pts
                              </span>
                            </div>
                          </div>
                        </div>
                      )
                    })}
                </div>

                {/* Show selected move + reasoning inline after tally when complete */}
                {selectedMove && currentPhase === 'complete' && reasoning && (
                  <div className="mt-3 p-3 bg-slate-700/30 rounded-lg border border-slate-600/30">
                    <p className="text-sm text-slate-300 leading-relaxed">{reasoning}</p>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function VoteRow({
  emoji,
  pieceType,
  square,
  personality,
  votedFor,
  weight,
  isWinnerVote,
  isExpanded,
  reasoning,
  onToggle,
  index,
}: {
  emoji: string
  pieceType: string
  square?: string
  personality?: Personality
  votedFor: string
  weight: number
  isWinnerVote: boolean
  isExpanded: boolean
  reasoning?: string
  onToggle: () => void
  index: number
}) {
  return (
    <>
      <tr
        className={`vote-card-enter cursor-pointer transition-colors duration-150 border-b border-slate-700/30
          ${isWinnerVote ? 'bg-green-500/10 hover:bg-green-500/15' : 'hover:bg-slate-700/40'}
        `}
        style={{ animationDelay: `${index * 60}ms` }}
        onClick={onToggle}
      >
        {/* Piece cell: emoji + type@square + personality bars */}
        <td className="py-2 pr-2">
          <div className="flex items-center gap-2">
            <span className="text-base leading-none">{emoji}</span>
            <div className="min-w-0">
              <span className="text-xs text-white font-medium capitalize">{pieceType}</span>
              {square && (
                <span className="text-[10px] text-slate-500 font-mono ml-1">@{square}</span>
              )}
            </div>
            {personality && <PersonalityMiniBar personality={personality} />}
          </div>
        </td>

        {/* Vote cell */}
        <td className="py-2 text-center">
          <span
            className={`text-xs font-bold px-2 py-0.5 rounded ${
              isWinnerVote
                ? 'bg-green-500/20 text-green-400'
                : 'bg-blue-500/15 text-blue-400'
            }`}
          >
            {votedFor}
          </span>
        </td>

        {/* Weight cell */}
        <td className="py-2 text-right">
          <span className="text-xs text-slate-500 font-mono">x{weight}</span>
        </td>
      </tr>

      {/* Expanded reasoning row */}
      {isExpanded && (
        <tr>
          <td colSpan={3} className="pb-2">
            <div className="px-2 py-2 bg-slate-700/30 rounded-lg text-sm text-slate-200 leading-relaxed">
              {reasoning || 'No reasoning provided'}
            </div>
          </td>
        </tr>
      )}
    </>
  )
}

function SectionHeader({
  title,
  count,
  subtitle,
}: {
  title: string
  count?: number
  subtitle?: string
}) {
  return (
    <div>
      <div className="flex items-center gap-2">
        <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">{title}</h4>
        {count !== undefined && (
          <span className="text-[10px] px-1.5 py-0.5 bg-slate-700/50 text-slate-500 rounded-full">
            {count}
          </span>
        )}
      </div>
      {subtitle && (
        <p className="text-[10px] text-slate-600 mt-0.5">{subtitle}</p>
      )}
    </div>
  )
}
