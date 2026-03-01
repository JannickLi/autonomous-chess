"""Game session state management."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from backend.chess_engine import ChessBoard
from backend.agents.base import MoveProposal


class GameState(Enum):
    """Possible states for a game session."""

    WAITING = "waiting"  # Waiting for players/configuration
    ACTIVE = "active"  # Game in progress
    PAUSED = "paused"  # Game paused
    COMPLETED = "completed"  # Game finished


@dataclass
class MoveRecord:
    """Record of a single move in the game."""

    move_number: int
    color: str
    move: str  # UCI notation
    san: str  # Standard algebraic notation
    fen_before: str
    fen_after: str
    timestamp: datetime = field(default_factory=datetime.now)
    proposals: list[MoveProposal] = field(default_factory=list)
    deliberation_summary: str = ""
    time_taken_ms: float = 0.0


@dataclass
class GameSession:
    """Represents an active game session."""

    id: str = field(default_factory=lambda: str(uuid4()))
    board: ChessBoard = field(default_factory=ChessBoard)
    state: GameState = GameState.WAITING
    strategy: str = "hybrid"

    # Player configuration
    white_player: str = "human"  # "human" or "agent"
    black_player: str = "agent"  # "human" or "agent"

    # Game history
    moves: list[MoveRecord] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    # Configuration
    config: dict[str, Any] = field(default_factory=dict)

    # External / ROS mode fields
    operation_mode: str = "simulation"  # "simulation" or "ros"
    last_detection_fen: str | None = None
    detected_pieces: dict[str, str] | None = None  # {square: piece}

    def __post_init__(self):
        if self.state == GameState.WAITING:
            self.state = GameState.ACTIVE

    @classmethod
    def from_fen(cls, fen: str, **kwargs) -> "GameSession":
        """Create a session from a FEN position."""
        session = cls(**kwargs)
        session.board = ChessBoard.from_fen(fen)
        return session

    @property
    def current_turn(self) -> str:
        """Get whose turn it is."""
        return self.board.turn_name

    @property
    def is_agent_turn(self) -> bool:
        """Check if it's the agent's turn to move."""
        if self.board.turn_name == "white":
            return self.white_player == "agent"
        return self.black_player == "agent"

    @property
    def is_game_over(self) -> bool:
        """Check if the game is over."""
        return self.board.is_game_over

    @property
    def result(self) -> str | None:
        """Get game result if over."""
        return self.board.get_result()

    def record_move(
        self,
        move: str,
        san: str,
        fen_before: str,
        fen_after: str,
        proposals: list[MoveProposal] | None = None,
        deliberation_summary: str = "",
        time_taken_ms: float = 0.0,
    ) -> MoveRecord:
        """Record a move in the game history."""
        record = MoveRecord(
            move_number=len(self.moves) + 1,
            color="white" if len(self.moves) % 2 == 0 else "black",
            move=move,
            san=san,
            fen_before=fen_before,
            fen_after=fen_after,
            proposals=proposals or [],
            deliberation_summary=deliberation_summary,
            time_taken_ms=time_taken_ms,
        )
        self.moves.append(record)
        self.updated_at = datetime.now()

        if self.is_game_over:
            self.state = GameState.COMPLETED

        return record

    def to_dict(self) -> dict[str, Any]:
        """Convert session to dictionary for API responses."""
        return {
            "id": self.id,
            "fen": self.board.fen,
            "state": self.state.value,
            "strategy": self.strategy,
            "current_turn": self.current_turn,
            "white_player": self.white_player,
            "black_player": self.black_player,
            "is_game_over": self.is_game_over,
            "result": self.result,
            "move_count": len(self.moves),
            "is_check": self.board.is_check,
            "legal_moves": self.board.get_legal_moves_uci(),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "operation_mode": self.operation_mode,
            "last_detection_fen": self.last_detection_fen,
            "detected_pieces": self.detected_pieces,
        }

    def get_move_history(self) -> list[dict[str, Any]]:
        """Get move history as list of dicts."""
        return [
            {
                "move_number": m.move_number,
                "color": m.color,
                "move": m.move,
                "san": m.san,
                "timestamp": m.timestamp.isoformat(),
                "has_deliberation": bool(m.proposals),
            }
            for m in self.moves
        ]
