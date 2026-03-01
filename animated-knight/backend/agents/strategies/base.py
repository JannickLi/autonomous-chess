"""Base strategy interface for agent decision-making."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator

from backend.chess_engine import ChessBoard

from ..base import MoveProposal, Vote


@dataclass
class DeliberationEvent:
    """An event during the deliberation process."""

    event_type: str  # 'proposal', 'vote', 'thought', 'decision'
    agent_id: str
    data: dict = field(default_factory=dict)


@dataclass
class DecisionResult:
    """The result of a strategy's decision process."""

    selected_move: str  # UCI notation
    reasoning: str
    proposals: list[MoveProposal] = field(default_factory=list)
    votes: list[Vote] = field(default_factory=list)
    deliberation_summary: str = ""


class DecisionStrategy(ABC):
    """Abstract base class for decision-making strategies."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the name of this strategy."""
        ...

    @abstractmethod
    async def decide(
        self, board: ChessBoard, **kwargs
    ) -> DecisionResult:
        """
        Make a decision about the best move.

        Args:
            board: The current chess board state
            **kwargs: Strategy-specific parameters

        Returns:
            DecisionResult with the selected move and metadata
        """
        ...

    @abstractmethod
    async def stream_deliberation(
        self, board: ChessBoard, **kwargs
    ) -> AsyncIterator[DeliberationEvent]:
        """
        Stream the deliberation process.

        Yields DeliberationEvents as the strategy progresses.
        The final event should contain the decision.
        """
        ...

    def validate_move(self, board: ChessBoard, move: str) -> bool:
        """Check if a move is valid."""
        return board.is_legal_move(move)
