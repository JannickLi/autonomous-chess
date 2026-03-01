"""Abstract interfaces for external API integrations."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class DetectionResult:
    """Result from the camera detection system."""

    success: bool
    fen: str | None = None
    pieces: dict[str, str] | None = None  # {square: piece} e.g., {"a1": "R", "e2": "P"}
    error: str | None = None


@dataclass
class MoveCommand:
    """Command to send to the robot system for move execution."""

    move: str  # UCI notation: "e2e4"
    from_square: str  # "e2"
    to_square: str  # "e4"
    piece_type: str  # "pawn", "knight", etc.
    piece_color: str  # "white" or "black"
    is_capture: bool  # True if capturing
    captured_piece: str | None  # Type of captured piece if any
    is_castling: bool  # True for castling moves
    is_en_passant: bool  # True for en passant
    is_promotion: bool  # True for pawn promotion
    promotion_piece: str | None  # "queen", "rook", etc.
    board_fen: str  # Current board state for context


@dataclass
class RobotResult:
    """Result from the robot system after move execution."""

    success: bool
    error: str | None = None


class DetectionClient(ABC):
    """Abstract interface for camera detection system."""

    @abstractmethod
    async def capture(self) -> DetectionResult:
        """Request board state capture from detection system.

        Returns:
            DetectionResult with the current board position as FEN
            and piece positions as a dictionary.
        """
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the detection system is available.

        Returns:
            True if the system is healthy and reachable.
        """
        ...


class RobotClient(ABC):
    """Abstract interface for robot control system."""

    @abstractmethod
    async def execute_move(self, command: MoveCommand) -> RobotResult:
        """Send move command to robot system.

        Args:
            command: The move command with all details needed for execution.

        Returns:
            RobotResult indicating success or failure.
        """
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the robot system is available.

        Returns:
            True if the system is healthy and reachable.
        """
        ...

    @abstractmethod
    async def home(self) -> RobotResult:
        """Send robot to home position.

        Returns:
            RobotResult indicating success or failure.
        """
        ...
