"""Base agent interface for chess-playing agents."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator

from backend.chess_engine import ChessBoard
from backend.llm import LLMConfig, LLMProvider


@dataclass
class MoveProposal:
    """A proposed move from an agent."""

    agent_id: str
    move: str  # UCI notation (internal use only)
    reasoning: str
    piece_type: str | None = None  # For piece agents
    piece_square: str | None = None  # For piece agents
    # Descriptive move info (used instead of UCI notation for agent voting)
    description: str | None = None  # e.g., "Bring Knight to a more active position"
    piece_impacts: dict[str, str] | None = None  # e.g., {"knight_g1": "High risk of being captured"}


@dataclass
class Vote:
    """A vote cast by an agent for a proposed move."""

    agent_id: str
    voted_for: str  # The choice (A, B, or C)
    reasoning: str | None = None


@dataclass
class AgentConfig:
    """Configuration for an agent."""

    agent_id: str
    llm_provider: str = "mistral"
    llm_model: str = "mistral-medium"
    temperature: float = 0.7
    system_prompt: str | None = None
    extra: dict = field(default_factory=dict)


class BaseAgent(ABC):
    """Abstract base class for all chess agents."""

    def __init__(
        self,
        agent_id: str,
        llm_provider: LLMProvider,
        config: AgentConfig | None = None,
    ):
        self.agent_id = agent_id
        self.llm_provider = llm_provider
        self.config = config or AgentConfig(agent_id=agent_id)
        self._llm_config = LLMConfig(
            model=self.config.llm_model,
            temperature=self.config.temperature,
        )

    @property
    @abstractmethod
    def agent_type(self) -> str:
        """Return the type of agent (e.g., 'piece', 'supervisor')."""
        ...

    @abstractmethod
    async def propose_move(self, board: ChessBoard) -> MoveProposal | None:
        """
        Propose a move for the current board state.

        Returns None if the agent cannot make a proposal (e.g., piece has no moves).
        """
        ...

    @abstractmethod
    async def stream_proposal(
        self, board: ChessBoard
    ) -> AsyncIterator[tuple[str, MoveProposal | None]]:
        """
        Stream the thought process while generating a proposal.

        Yields:
            Tuples of (thought_chunk, proposal) where proposal is None until final.
        """
        ...

    async def evaluate_move(
        self, board: ChessBoard, move: str
    ) -> tuple[float, str]:
        """
        Evaluate a proposed move and return a score with reasoning.

        Returns:
            Tuple of (score from 0-1, reasoning string)
        """
        prompt = self._build_evaluate_prompt(board, move)
        response = await self.llm_provider.complete(prompt, self._llm_config)
        return self._parse_evaluation(response.content)

    async def vote(
        self, board: ChessBoard, proposals: list[MoveProposal]
    ) -> Vote:
        """
        Vote on a set of proposed moves.

        Default implementation evaluates each proposal and votes for the best.
        """
        if not proposals:
            raise ValueError("No proposals to vote on")

        best_score = -1.0
        best_choice = "A"  # Default to first option
        best_reasoning = ""

        choices = ["A", "B", "C"]
        for i, proposal in enumerate(proposals[:3]):
            score, reasoning = await self.evaluate_move(board, proposal.move)
            if score > best_score:
                best_score = score
                best_choice = choices[i]
                best_reasoning = reasoning

        return Vote(
            agent_id=self.agent_id,
            voted_for=best_choice,
            reasoning=best_reasoning,
        )

    async def deliberate(
        self,
        board: ChessBoard,
        proposals: list[MoveProposal],
        context: str = "",
    ) -> str:
        """
        Generate deliberation thoughts about the given proposals.

        This is used for the supervisor to synthesize proposals.
        """
        prompt = self._build_deliberation_prompt(board, proposals, context)
        response = await self.llm_provider.complete(prompt, self._llm_config)
        return response.content

    def _build_evaluate_prompt(self, board: ChessBoard, move: str) -> str:
        """Build prompt for move evaluation."""
        return f"""You are a chess expert and entertaining commentator. Evaluate the following move.

Current position (FEN): {board.fen}
Turn: {board.turn_name}
Move to evaluate: {move}

Board visualization:
{board.get_board_visual()}

Evaluate this move on a scale of 0.0 to 1.0 (0=bad, 1=excellent).

Respond in this format:
SCORE: <number between 0.0 and 1.0>
REASONING: <1-2 punchy sentences with personality — make it vivid and fun>"""

    def _build_deliberation_prompt(
        self, board: ChessBoard, proposals: list[MoveProposal], context: str
    ) -> str:
        """Build prompt for deliberation."""
        proposals_text = "\n".join(
            f"- {p.description or p.move}: {p.reasoning}"
            for p in proposals
        )
        return f"""You are a chess expert and entertaining commentator deliberating on the best move.

Current position (FEN): {board.fen}
Turn: {board.turn_name}

Board visualization:
{board.get_board_visual()}

Proposed moves:
{proposals_text}

{context}

Give your take in 2-3 punchy sentences — be vivid and opinionated about which move is best and why."""

    def _parse_evaluation(self, response: str) -> tuple[float, str]:
        """Parse evaluation response into score and reasoning."""
        lines = response.strip().split("\n")
        score = 0.5
        reasoning = response

        for line in lines:
            # Strip markdown formatting (**, *, etc.) before checking
            clean_line = line.replace("**", "").replace("*", "").strip()
            if clean_line.upper().startswith("SCORE:"):
                try:
                    score_str = clean_line.split(":", 1)[1].strip().split()[0]
                    score = float(score_str)
                    score = max(0.0, min(1.0, score))  # Clamp to 0-1
                except (ValueError, IndexError):
                    pass
            elif clean_line.upper().startswith("REASONING:"):
                reasoning = clean_line.split(":", 1)[1].strip()

        return score, reasoning
