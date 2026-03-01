import { create } from 'zustand'

export interface Proposal {
  agentId: string
  choice: string  // A, B, or C
  description: string
  reasoning: string
  pieceImpacts?: Record<string, string>
  move?: string  // UCI move (internal, not shown to agents)
}

export interface Personality {
  self_preservation: number
  personal_glory: number
  team_victory: number
  aggression: number
  positional_dominance: number
  cooperation: number
}

export interface Vote {
  agentId: string
  votedFor: string  // A, B, or C
  weight?: number
  pieceType?: string
  pieceSquare?: string
  reasoning?: string
  personality?: Personality
}

export interface ThoughtChunk {
  agentId: string
  thought: string
  timestamp: number
}

interface DeliberationState {
  // Current deliberation
  isDeliberating: boolean
  activeAgents: string[]
  currentPhase: 'idle' | 'proposing' | 'voting' | 'synthesis' | 'complete'

  // Proposals
  proposals: Proposal[]

  // Votes
  votes: Vote[]
  voteSummary: Record<string, number>

  // Streaming thoughts
  thoughts: ThoughtChunk[]
  streamingAgentId: string | null
  currentThought: string

  // Final decision
  selectedMove: string | null
  winningChoice: string | null  // A, B, or C
  reasoning: string

  // Actions
  startDeliberation: (agents: string[]) => void
  addProposal: (proposal: Proposal) => void
  addVote: (vote: Vote) => void
  addThought: (agentId: string, thought: string) => void
  setPhase: (phase: DeliberationState['currentPhase']) => void
  setSelectedMove: (move: string, winningChoice: string, reasoning: string) => void
  reset: () => void
}

export const useDeliberationStore = create<DeliberationState>((set) => ({
  // Initial state
  isDeliberating: false,
  activeAgents: [],
  currentPhase: 'idle',
  proposals: [],
  votes: [],
  voteSummary: {},
  thoughts: [],
  streamingAgentId: null,
  currentThought: '',
  selectedMove: null,
  winningChoice: null,
  reasoning: '',

  startDeliberation: (agents) => {
    set({
      isDeliberating: true,
      activeAgents: agents,
      currentPhase: 'proposing',
      proposals: [],
      votes: [],
      voteSummary: {},
      thoughts: [],
      currentThought: '',
      selectedMove: null,
    })
  },

  addProposal: (proposal) => {
    set((state) => {
      // Deduplicate by choice letter — each choice (A/B/C) appears at most once
      const existing = state.proposals.findIndex((p) => p.choice === proposal.choice)
      if (existing !== -1) {
        const updated = [...state.proposals]
        updated[existing] = proposal
        return { proposals: updated }
      }
      return { proposals: [...state.proposals, proposal] }
    })
  },

  addVote: (vote) => {
    set((state) => {
      const newVotes = [...state.votes, vote]
      const newSummary = { ...state.voteSummary }
      // Simple weighted vote (no confidence)
      const score = vote.weight || 1
      newSummary[vote.votedFor] = (newSummary[vote.votedFor] || 0) + score
      return {
        votes: newVotes,
        voteSummary: newSummary,
      }
    })
  },

  addThought: (agentId, thought) => {
    set((state) => ({
      thoughts: [
        ...state.thoughts,
        { agentId, thought, timestamp: Date.now() },
      ],
      streamingAgentId: agentId,
      currentThought: state.streamingAgentId === agentId
        ? state.currentThought + thought
        : thought,
    }))
  },

  setPhase: (phase) => {
    set({ currentPhase: phase })
  },

  setSelectedMove: (move, winningChoice, reasoning) => {
    set({
      selectedMove: move,
      winningChoice,
      reasoning,
      currentPhase: 'complete',
      isDeliberating: false,
    })
  },

  reset: () => {
    set({
      isDeliberating: false,
      activeAgents: [],
      currentPhase: 'idle',
      proposals: [],
      votes: [],
      voteSummary: {},
      thoughts: [],
      streamingAgentId: null,
      currentThought: '',
      selectedMove: null,
      winningChoice: null,
      reasoning: '',
    })
  },
}))
