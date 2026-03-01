"""Supervisor strategy where a central agent coordinates piece agents."""

import asyncio
from typing import AsyncIterator

from backend.chess_engine import ChessBoard
from backend.llm import LLMProvider, get_provider

from ..base import AgentConfig, MoveProposal
from ..piece_agent import PieceAgent
from ..supervisor_agent import SupervisorAgent
from .base import DecisionResult, DecisionStrategy, DeliberationEvent


class SupervisorStrategy(DecisionStrategy):
    """
    Supervisor strategy where a central agent coordinates decisions.

    Process:
    1. Piece agents propose moves (optionally in parallel)
    2. Supervisor reviews all proposals
    3. Supervisor synthesizes and makes final decision
    """

    def __init__(
        self,
        llm_provider: LLMProvider | None = None,
        provider_name: str = "mistral",
        agent_config: AgentConfig | None = None,
        supervisor_config: AgentConfig | None = None,
    ):
        self._provider_name = provider_name
        self._llm_provider = llm_provider
        self.agent_config = agent_config
        self.supervisor_config = supervisor_config

    @property
    def name(self) -> str:
        return "supervisor"

    @property
    def llm_provider(self) -> LLMProvider:
        if self._llm_provider is None:
            self._llm_provider = get_provider(self._provider_name)
        return self._llm_provider

    async def decide(self, board: ChessBoard, **kwargs) -> DecisionResult:
        """Run supervisor-based decision process."""
        # Create piece agents
        piece_agents = PieceAgent.create_for_movable_pieces(
            board, self.llm_provider, self.agent_config
        )

        # Create supervisor
        supervisor = SupervisorAgent(
            self.llm_provider, self.supervisor_config
        )

        # Gather proposals from piece agents in parallel
        if piece_agents:
            proposal_tasks = [agent.propose_move(board) for agent in piece_agents]
            proposal_results = await asyncio.gather(*proposal_tasks)
            proposals = [p for p in proposal_results if p is not None]
        else:
            proposals = []

        # Supervisor synthesizes proposals
        final_proposal = await supervisor.synthesize_proposals(board, proposals)

        return DecisionResult(
            selected_move=final_proposal.move,
            reasoning=final_proposal.reasoning,
            proposals=proposals,
            deliberation_summary=self._build_summary(proposals, final_proposal),
        )

    async def stream_deliberation(
        self, board: ChessBoard, **kwargs
    ) -> AsyncIterator[DeliberationEvent]:
        """Stream the supervisor deliberation process."""
        # Create piece agents
        piece_agents = PieceAgent.create_for_movable_pieces(
            board, self.llm_provider, self.agent_config
        )

        # Create supervisor
        supervisor = SupervisorAgent(
            self.llm_provider, self.supervisor_config
        )

        yield DeliberationEvent(
            event_type="deliberation_started",
            agent_id="supervisor",
            data={
                "active_agents": [a.agent_id for a in piece_agents],
                "strategy": "supervisor",
            },
        )

        # Phase 1: Gather proposals from pieces
        proposals: list[MoveProposal] = []

        if piece_agents:
            yield DeliberationEvent(
                event_type="phase_started",
                agent_id="supervisor",
                data={"phase": "gathering_proposals"},
            )

            for agent in piece_agents:
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

        # Phase 2: Supervisor synthesis
        yield DeliberationEvent(
            event_type="phase_started",
            agent_id="supervisor",
            data={"phase": "synthesis"},
        )

        yield DeliberationEvent(
            event_type="agent_thinking",
            agent_id="supervisor",
            data={"role": "synthesizing proposals"},
        )

        final_proposal = None
        async for thought, prop in supervisor.stream_synthesis(board, proposals):
            if thought:
                yield DeliberationEvent(
                    event_type="agent_thought",
                    agent_id="supervisor",
                    data={"thought": thought, "is_streaming": True},
                )
            if prop is not None:
                final_proposal = prop

        if final_proposal:
            yield DeliberationEvent(
                event_type="supervisor_decision",
                agent_id="supervisor",
                data={
                    "move": final_proposal.move,
                    "reasoning": final_proposal.reasoning,
                },
            )

            yield DeliberationEvent(
                event_type="deliberation_complete",
                agent_id="supervisor",
                data={
                    "selected_move": final_proposal.move,
                    "reasoning": final_proposal.reasoning,
                },
            )
        else:
            # Fallback
            legal = board.get_legal_moves_uci()
            yield DeliberationEvent(
                event_type="deliberation_complete",
                agent_id="supervisor",
                data={
                    "selected_move": legal[0] if legal else "",
                    "reasoning": "Supervisor could not reach decision",
                },
            )

    def _build_summary(
        self, proposals: list[MoveProposal], final: MoveProposal
    ) -> str:
        """Build a summary of the supervisor deliberation."""
        lines = ["## Supervisor Deliberation Summary\n"]

        if proposals:
            lines.append("### Piece Agent Proposals")
            for p in proposals:
                lines.append(
                    f"- **{p.agent_id}**: {p.description or p.move} - {p.reasoning}"
                )
            lines.append("")

        lines.append("### Supervisor Decision")
        lines.append(f"**Selected Move**: {final.description or final.move}")
        lines.append(f"**Reasoning**: {final.reasoning}")

        return "\n".join(lines)
