"""Democratic voting strategy where pieces propose and vote."""

import asyncio
from collections import defaultdict
from typing import AsyncIterator

from backend.chess_engine import ChessBoard
from backend.llm import LLMProvider, get_provider

from ..base import AgentConfig, MoveProposal, Vote
from ..piece_agent import PieceAgent
from .base import DecisionResult, DecisionStrategy, DeliberationEvent


class DemocraticStrategy(DecisionStrategy):
    """
    Democratic strategy where all movable pieces propose and vote.

    Process:
    1. Each piece with legal moves proposes its best move
    2. All pieces vote on all proposals
    3. Votes are weighted by piece value
    4. Majority wins
    """

    # Default piece weights for voting
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
        all_pieces_vote: bool = True,  # If True, all pieces vote (not just movable ones)
    ):
        self._provider_name = provider_name
        self._llm_provider = llm_provider
        self.weights = weights or self.DEFAULT_WEIGHTS
        self.agent_config = agent_config
        self.all_pieces_vote = all_pieces_vote

    @property
    def name(self) -> str:
        return "democratic"

    @property
    def llm_provider(self) -> LLMProvider:
        if self._llm_provider is None:
            self._llm_provider = get_provider(self._provider_name)
        return self._llm_provider

    async def decide(self, board: ChessBoard, **kwargs) -> DecisionResult:
        """Run democratic decision process."""
        # Create piece agents for movable pieces (proposers)
        proposer_agents = PieceAgent.create_for_movable_pieces(
            board, self.llm_provider, self.agent_config
        )

        # Create voter agents (all pieces or just movable ones)
        if self.all_pieces_vote:
            voter_agents = PieceAgent.create_for_all_pieces(
                board, self.llm_provider, self.agent_config
            )
        else:
            voter_agents = proposer_agents

        agents = proposer_agents  # For backward compatibility

        if not agents:
            # No movable pieces (shouldn't happen in valid game)
            legal = board.get_legal_moves_uci()
            return DecisionResult(
                selected_move=legal[0] if legal else "",
                reasoning="No pieces available for deliberation",
            )

        # Phase 1: Gather proposals from all pieces in parallel
        proposal_tasks = [agent.propose_move(board) for agent in agents]
        proposal_results = await asyncio.gather(*proposal_tasks)
        proposals = [p for p in proposal_results if p is not None]

        if not proposals:
            legal = board.get_legal_moves_uci()
            return DecisionResult(
                selected_move=legal[0] if legal else "",
                reasoning="No proposals generated, using first legal move",
            )

        # Phase 2: All voter agents vote on proposals
        vote_tasks = [agent.vote(board, proposals) for agent in voter_agents]
        votes = await asyncio.gather(*vote_tasks)

        # Phase 3: Count weighted votes (simple weight, no confidence)
        vote_counts: dict[str, float] = defaultdict(float)

        for agent, vote in zip(voter_agents, votes):
            weight = self.weights.get(agent.piece.name, 1)
            vote_counts[vote.voted_for] += weight  # Simple weighted vote

        # Find winner - map A/B/C back to moves
        best_choice = max(vote_counts.keys(), key=lambda c: vote_counts[c])
        choice_to_idx = {"A": 0, "B": 1, "C": 2}
        winning_idx = choice_to_idx.get(best_choice, 0)
        best_move = proposals[winning_idx].move if winning_idx < len(proposals) else proposals[0].move

        # Build reasoning
        winning_proposal = proposals[winning_idx] if winning_idx < len(proposals) else proposals[0]
        reasoning = f"Democratic vote selected option {best_choice}"
        reasoning += f" (proposed by {winning_proposal.agent_id})"

        return DecisionResult(
            selected_move=best_move,
            reasoning=reasoning,
            proposals=proposals,
            votes=list(votes),
            deliberation_summary=self._build_summary(proposals, list(votes), vote_counts),
        )

    async def stream_deliberation(
        self, board: ChessBoard, **kwargs
    ) -> AsyncIterator[DeliberationEvent]:
        """Stream the democratic deliberation process."""
        # Create piece agents for movable pieces (proposers)
        proposer_agents = PieceAgent.create_for_movable_pieces(
            board, self.llm_provider, self.agent_config
        )

        # Create voter agents (all pieces or just movable ones)
        if self.all_pieces_vote:
            voter_agents = PieceAgent.create_for_all_pieces(
                board, self.llm_provider, self.agent_config
            )
        else:
            voter_agents = proposer_agents

        if not proposer_agents:
            yield DeliberationEvent(
                event_type="error",
                agent_id="system",
                data={"message": "No movable pieces"},
            )
            return

        yield DeliberationEvent(
            event_type="deliberation_started",
            agent_id="system",
            data={
                "active_agents": [a.agent_id for a in proposer_agents],
                "voter_agents": [a.agent_id for a in voter_agents],
            },
        )

        # Stream proposals
        proposals = []
        for agent in proposer_agents:
            yield DeliberationEvent(
                event_type="agent_thinking",
                agent_id=agent.agent_id,
                data={"piece": agent.piece.name, "square": agent.piece.square_name},
            )

            thoughts = []
            proposal = None
            async for thought, prop in agent.stream_proposal(board):
                if thought:
                    thoughts.append(thought)
                    yield DeliberationEvent(
                        event_type="agent_thought",
                        agent_id=agent.agent_id,
                        data={"thought": thought, "is_streaming": True},
                    )
                if prop is not None:
                    proposal = prop

            if proposal:
                proposals.append(proposal)
                yield DeliberationEvent(
                    event_type="agent_proposal",
                    agent_id=agent.agent_id,
                    data={
                        "move": proposal.move,
                        "reasoning": proposal.reasoning,
                    },
                )

        if not proposals:
            legal = board.get_legal_moves_uci()
            yield DeliberationEvent(
                event_type="deliberation_complete",
                agent_id="system",
                data={
                    "selected_move": legal[0] if legal else "",
                    "reasoning": "No proposals, using fallback",
                },
            )
            return

        # Voting phase
        yield DeliberationEvent(
            event_type="voting_started",
            agent_id="system",
            data={"proposals": [p.move for p in proposals]},
        )

        vote_counts: dict[str, float] = defaultdict(float)
        votes = []

        # Collect votes in parallel for speed, then yield events
        vote_tasks = [agent.vote(board, proposals) for agent in voter_agents]
        vote_results = await asyncio.gather(*vote_tasks)

        for agent, vote in zip(voter_agents, vote_results):
            votes.append(vote)
            weight = self.weights.get(agent.piece.name, 1)
            vote_counts[vote.voted_for] += weight  # Simple weighted vote

            yield DeliberationEvent(
                event_type="vote_cast",
                agent_id=agent.agent_id,
                data={
                    "voted_for": vote.voted_for,
                    "weight": weight,
                    "piece_type": agent.piece.name,
                    "piece_square": agent.piece.square_name,
                    "reasoning": vote.reasoning,
                },
            )

        # Determine winner - map A/B/C back to moves
        best_choice = max(vote_counts.keys(), key=lambda c: vote_counts[c])
        choice_to_idx = {"A": 0, "B": 1, "C": 2}
        winning_idx = choice_to_idx.get(best_choice, 0)
        best_move = proposals[winning_idx].move if winning_idx < len(proposals) else proposals[0].move

        # Build detailed voting breakdown
        voting_breakdown = [
            {
                "agent_id": agent.agent_id,
                "piece_type": agent.piece.name,
                "piece_square": agent.piece.square_name,
                "voted_for": vote.voted_for,
                "weight": self.weights.get(agent.piece.name, 1),
            }
            for agent, vote in zip(voter_agents, votes)
        ]

        yield DeliberationEvent(
            event_type="deliberation_complete",
            agent_id="system",
            data={
                "selected_move": best_move,
                "winning_choice": best_choice,
                "vote_summary": dict(vote_counts),
                "voting_breakdown": voting_breakdown,
                "total_voters": len(voter_agents),
            },
        )

    def _build_summary(
        self,
        proposals: list[MoveProposal],
        votes: list[Vote],
        vote_counts: dict[str, float],
    ) -> str:
        """Build a human-readable summary of the deliberation."""
        lines = ["## Democratic Deliberation Summary\n"]

        lines.append("### Options")
        choices = ["A", "B", "C"]
        for i, p in enumerate(proposals[:3]):
            lines.append(f"- **Option {choices[i]}** ({p.agent_id}): {p.description or p.reasoning}")

        lines.append("\n### Vote Tally")
        sorted_votes = sorted(vote_counts.items(), key=lambda x: x[1], reverse=True)
        for choice, count in sorted_votes:
            lines.append(f"- Option {choice}: {count:.0f} weighted votes")

        return "\n".join(lines)
