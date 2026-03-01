"""Hybrid strategy: Supervisor analyzes and describes moves, pieces vote A/B/C based on personality."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import TYPE_CHECKING, AsyncIterator

from backend.chess_engine import ChessBoard
from backend.core.config import get_settings
from backend.llm import LLMProvider, get_provider

from ..base import AgentConfig, MoveProposal, Vote
from ..personality import PersonalityWeights
from ..piece_agent import PieceAgent, reset_debug_flag
from ..supervisor_agent import SupervisorAgent
from .base import DecisionResult, DecisionStrategy, DeliberationEvent

if TYPE_CHECKING:
    from backend.chess_engine.engine_analyzer import EngineAnalyzer


class HybridStrategy(DecisionStrategy):
    """
    Hybrid strategy combining supervisor analysis with personality-based A/B/C voting.

    Process:
    1. Supervisor (reasoning model) analyzes position deeply and proposes 3 moves
    2. Each move is described strategically with impact on each piece
    3. Pieces vote A/B/C based on description and personal impact, NOT UCI notation
    4. Simple majority wins (no confidence weighting)

    Piece personalities affect how they evaluate moves:
    - Self-preservation: Prefer safe moves
    - Personal glory: Prefer impactful/capturing moves
    - Team victory: Prefer objectively best moves
    - Aggression: Prefer attacking moves
    - Positional dominance: Prefer moves that control squares
    - Cooperation: Prefer moves that support teammates
    """

    # Default piece weights for voting power
    DEFAULT_WEIGHTS = {
        "king": 10,
        "queen": 9,
        "rook": 5,
        "bishop": 3,
        "knight": 3,
        "pawn": 1,
    }

    def __init__(
        self,
        llm_provider: LLMProvider | None = None,
        provider_name: str = "mistral",
        weights: dict[str, int] | None = None,
        agent_config: AgentConfig | None = None,
        supervisor_config: AgentConfig | None = None,
        num_candidates: int = 3,
        all_pieces_vote: bool = True,
        personality_overrides: dict[str, dict[str, float]] | None = None,
        engine_analyzer: "EngineAnalyzer | None" = None,
    ):
        """
        Initialize the hybrid strategy.

        Args:
            llm_provider: The LLM provider to use (for agents)
            provider_name: Name of provider to use if llm_provider not given
            weights: Voting power weights per piece type
            agent_config: Config for piece agents (smaller model)
            supervisor_config: Config for supervisor agent (reasoning model)
            num_candidates: Number of candidate moves supervisor proposes (always 3)
            all_pieces_vote: If True, all pieces vote (not just movable ones)
            personality_overrides: Override personality weights per piece type
                Example: {"queen": {"aggression": 0.9, "self_preservation": 0.3}}
            engine_analyzer: Optional Stockfish engine analyzer for move analysis
        """
        self._provider_name = provider_name
        self._llm_provider = llm_provider
        self.weights = weights or self.DEFAULT_WEIGHTS
        self.agent_config = agent_config
        self.supervisor_config = supervisor_config
        self.num_candidates = 3  # Always 3 for A/B/C voting
        self.all_pieces_vote = all_pieces_vote
        self.personality_overrides = personality_overrides
        self._engine_analyzer = engine_analyzer
        self._engine_initialized = False

    @property
    def name(self) -> str:
        return "hybrid"

    @property
    def llm_provider(self) -> LLMProvider:
        if self._llm_provider is None:
            self._llm_provider = get_provider(self._provider_name)
        return self._llm_provider

    @property
    def engine_analyzer(self) -> "EngineAnalyzer | None":
        """Get or lazily initialize the engine analyzer based on config."""
        if self._engine_analyzer is not None:
            return self._engine_analyzer

        if self._engine_initialized:
            return None

        self._engine_initialized = True
        settings = get_settings()

        if not settings.use_engine:
            print("[HybridStrategy] Engine disabled via USE_ENGINE=false")
            return None

        # Lazy import to avoid circular dependencies
        from backend.chess_engine.engine_analyzer import EngineAnalyzer

        self._engine_analyzer = EngineAnalyzer(
            stockfish_path=settings.stockfish_path,
            depth=settings.stockfish_depth,
            time_limit_ms=settings.stockfish_time_limit_ms,
        )

        if self._engine_analyzer.is_available:
            print(f"[HybridStrategy] Stockfish engine available at: {self._engine_analyzer._stockfish_path}")
        else:
            print("[HybridStrategy] Stockfish not found, using LLM-only analysis")
            self._engine_analyzer = None

        return self._engine_analyzer

    async def decide(self, board: ChessBoard, **kwargs) -> DecisionResult:
        """Run hybrid decision process with A/B/C voting."""
        # Reset debug flag to show one agent interaction per move
        reset_debug_flag()

        # Create supervisor with reasoning model config
        supervisor = SupervisorAgent(self.llm_provider, self.supervisor_config)

        # Phase 1: Supervisor analyzes position and proposes 3 descriptive candidates
        # Pass engine analyzer for improved move quality when available
        candidates = await supervisor.analyze_position(board, self.engine_analyzer)

        if not candidates:
            legal = board.get_legal_moves_uci()
            return DecisionResult(
                selected_move=legal[0] if legal else "",
                reasoning="No candidates proposed, using first legal move",
                proposals=[],
            )

        # Phase 2: Create voter agents with personalities
        if self.all_pieces_vote:
            voter_agents = PieceAgent.create_for_all_pieces(
                board, self.llm_provider, self.agent_config,
                personality_overrides=self.personality_overrides,
            )
        else:
            voter_agents = PieceAgent.create_for_movable_pieces(
                board, self.llm_provider, self.agent_config,
                personality_overrides=self.personality_overrides,
            )

        if not voter_agents:
            return DecisionResult(
                selected_move=candidates[0].move,
                reasoning=f"Supervisor's top choice: {candidates[0].reasoning}",
                proposals=candidates,
            )

        # Phase 3: Pieces vote A/B/C on candidates (parallel)
        vote_tasks = [agent.vote(board, candidates) for agent in voter_agents]
        votes = await asyncio.gather(*vote_tasks)

        # Tally weighted votes (A/B/C -> weighted count)
        vote_counts: dict[str, float] = defaultdict(float)
        for agent, vote in zip(voter_agents, votes):
            weight = self.weights.get(agent.piece.name, 1)
            vote_counts[vote.voted_for] += weight  # Simple weighted vote, no confidence

        # Find winner (A, B, or C)
        best_choice = max(vote_counts.keys(), key=lambda c: vote_counts[c])

        # Map choice back to actual move
        choice_to_idx = {"A": 0, "B": 1, "C": 2}
        winning_idx = choice_to_idx.get(best_choice, 0)
        winning_candidate = candidates[winning_idx] if winning_idx < len(candidates) else candidates[0]

        reasoning = winning_candidate.description or winning_candidate.reasoning

        # Debug: Show final vote tally
        print("\n" + "=" * 100)
        print("DEBUG: FINAL VOTE TALLY")
        print("=" * 100)
        print("\n--- VOTE COUNTS ---")
        for choice in ["A", "B", "C"]:
            count = vote_counts.get(choice, 0)
            print(f"  Option {choice}: {count:.0f} weighted votes")
        print(f"\n--- WINNER: Option {best_choice} ---")
        print(f"  UCI Move: {winning_candidate.move}")
        print(f"  Description: {winning_candidate.description}")
        print("\n--- ALL VOTES ---")
        for agent, vote in zip(voter_agents, votes):
            print(f"  {agent.agent_id} ({agent.piece.name}): voted {vote.voted_for} - {vote.reasoning}")
        print("\n" + "=" * 100 + "\n")

        return DecisionResult(
            selected_move=winning_candidate.move,
            reasoning=reasoning,
            proposals=candidates,
            votes=list(votes),
            deliberation_summary=self._build_summary(candidates, list(votes), vote_counts),
        )

    async def _get_supervisor_analysis(
        self, supervisor: SupervisorAgent, board: ChessBoard
    ) -> list[MoveProposal]:
        """Get detailed analysis with 3 candidate moves from supervisor."""
        return await supervisor.analyze_position(board, self.engine_analyzer)

    async def stream_deliberation(
        self, board: ChessBoard, **kwargs
    ) -> AsyncIterator[DeliberationEvent]:
        """Stream the hybrid deliberation process with A/B/C voting."""
        # Reset debug flag to show one agent interaction per move
        reset_debug_flag()

        supervisor = SupervisorAgent(self.llm_provider, self.supervisor_config)

        yield DeliberationEvent(
            event_type="deliberation_started",
            agent_id="supervisor",
            data={"strategy": "hybrid", "phase": "supervisor_analysis"},
        )

        # Phase 1: Supervisor analyzes position
        yield DeliberationEvent(
            event_type="phase_started",
            agent_id="supervisor",
            data={"phase": "analyzing_position", "num_candidates": 3},
        )

        yield DeliberationEvent(
            event_type="agent_thinking",
            agent_id="supervisor",
            data={"role": "analyzing position and proposing strategic options"},
        )

        # Pass engine analyzer for improved move quality when available
        candidates = await supervisor.analyze_position(board, self.engine_analyzer)

        choices = ["A", "B", "C"]
        for i, candidate in enumerate(candidates[:3]):
            yield DeliberationEvent(
                event_type="agent_proposal",
                agent_id="supervisor",
                data={
                    "choice": choices[i],
                    "move": candidate.move,
                    "description": candidate.description,
                    "reasoning": candidate.reasoning,
                    "piece_impacts": candidate.piece_impacts,
                },
            )

        if not candidates:
            legal = board.get_legal_moves_uci()
            yield DeliberationEvent(
                event_type="deliberation_complete",
                agent_id="supervisor",
                data={
                    "selected_move": legal[0] if legal else "",
                    "reasoning": "No candidates, using fallback",
                },
            )
            return

        # Create voter agents with personalities
        if self.all_pieces_vote:
            voter_agents = PieceAgent.create_for_all_pieces(
                board, self.llm_provider, self.agent_config,
                personality_overrides=self.personality_overrides,
            )
        else:
            voter_agents = PieceAgent.create_for_movable_pieces(
                board, self.llm_provider, self.agent_config,
                personality_overrides=self.personality_overrides,
            )

        if not voter_agents:
            yield DeliberationEvent(
                event_type="deliberation_complete",
                agent_id="supervisor",
                data={
                    "selected_move": candidates[0].move,
                    "reasoning": "No pieces to vote, using supervisor's top choice",
                },
            )
            return

        # Phase 2: A/B/C Voting
        yield DeliberationEvent(
            event_type="phase_started",
            agent_id="system",
            data={
                "phase": "voting",
                "options": ["A", "B", "C"],
                "voters": [a.agent_id for a in voter_agents],
            },
        )

        vote_counts: dict[str, float] = defaultdict(float)
        votes = []

        # Collect votes in parallel
        vote_tasks = [agent.vote(board, candidates) for agent in voter_agents]
        vote_results = await asyncio.gather(*vote_tasks)

        for agent, vote in zip(voter_agents, vote_results):
            votes.append(vote)
            weight = self.weights.get(agent.piece.name, 1)
            vote_counts[vote.voted_for] += weight  # Simple weighted vote

            # Include personality info in the event
            personality_summary = {
                "self_preservation": agent.personality.self_preservation,
                "personal_glory": agent.personality.personal_glory,
                "team_victory": agent.personality.team_victory,
                "aggression": agent.personality.aggression,
                "positional_dominance": agent.personality.positional_dominance,
                "cooperation": agent.personality.cooperation,
            }

            yield DeliberationEvent(
                event_type="vote_cast",
                agent_id=agent.agent_id,
                data={
                    "voted_for": vote.voted_for,  # A, B, or C
                    "weight": weight,
                    "piece_type": agent.piece.name,
                    "piece_square": agent.piece.square_name,
                    "reasoning": vote.reasoning,
                    "personality": personality_summary,
                },
            )

        # Determine winner (A, B, or C)
        best_choice = max(vote_counts.keys(), key=lambda c: vote_counts[c])
        choice_to_idx = {"A": 0, "B": 1, "C": 2}
        winning_idx = choice_to_idx.get(best_choice, 0)
        winning_candidate = candidates[winning_idx] if winning_idx < len(candidates) else candidates[0]

        reasoning = winning_candidate.description or winning_candidate.reasoning

        # Build detailed voting breakdown
        voting_breakdown = [
            {
                "agent_id": agent.agent_id,
                "piece_type": agent.piece.name,
                "piece_square": agent.piece.square_name,
                "voted_for": vote.voted_for,
                "weight": self.weights.get(agent.piece.name, 1),
                "reasoning": vote.reasoning,
            }
            for agent, vote in zip(voter_agents, votes)
        ]

        yield DeliberationEvent(
            event_type="deliberation_complete",
            agent_id="system",
            data={
                "selected_move": winning_candidate.move,
                "winning_choice": best_choice,
                "reasoning": reasoning,
                "vote_summary": dict(vote_counts),
                "voting_breakdown": voting_breakdown,
                "total_voters": len(voter_agents),
            },
        )

    def _build_summary(
        self,
        candidates: list[MoveProposal],
        votes: list[Vote],
        vote_counts: dict[str, float],
    ) -> str:
        """Build a human-readable summary."""
        lines = ["## Hybrid Deliberation Summary\n"]

        lines.append("### Strategic Options")
        choices = ["A", "B", "C"]
        for i, c in enumerate(candidates[:3]):
            description = c.description or c.reasoning
            lines.append(f"**Option {choices[i]}**: {description}")

        lines.append("\n### Vote Tally")
        sorted_votes = sorted(vote_counts.items(), key=lambda x: x[1], reverse=True)
        for choice, count in sorted_votes:
            lines.append(f"- Option {choice}: {count:.0f} weighted votes")

        return "\n".join(lines)
