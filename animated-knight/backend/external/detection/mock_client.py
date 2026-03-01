"""Mock detection client for development and testing."""

import asyncio
import chess

from backend.external.interfaces import DetectionClient, DetectionResult


class MockDetectionClient(DetectionClient):
    """Mock implementation of the detection client for testing.

    Returns configurable FEN positions and generates piece mappings.
    """

    # Map from chess.Piece symbol to piece letter
    PIECE_SYMBOLS = {
        "P": "P",
        "N": "N",
        "B": "B",
        "R": "R",
        "Q": "Q",
        "K": "K",
        "p": "p",
        "n": "n",
        "b": "b",
        "r": "r",
        "q": "q",
        "k": "k",
    }

    def __init__(
        self,
        default_fen: str | None = None,
        capture_delay: float = 0.5,
        should_fail: bool = False,
        error_message: str = "Detection failed",
    ):
        """Initialize the mock detection client.

        Args:
            default_fen: The FEN to return on capture. If None, uses starting position.
            capture_delay: Simulated delay in seconds for capture operation.
            should_fail: If True, capture will return an error.
            error_message: Error message to return when should_fail is True.
        """
        self._default_fen = default_fen or chess.STARTING_FEN
        self._current_fen = self._default_fen
        self._capture_delay = capture_delay
        self._should_fail = should_fail
        self._error_message = error_message
        self._is_healthy = True

    def set_fen(self, fen: str) -> None:
        """Set the FEN position to return on next capture.

        Args:
            fen: Valid FEN string.
        """
        # Validate FEN
        board = chess.Board(fen)
        self._current_fen = board.fen()

    def set_should_fail(self, should_fail: bool, error_message: str | None = None) -> None:
        """Configure whether capture should fail.

        Args:
            should_fail: If True, next capture will fail.
            error_message: Optional error message to use.
        """
        self._should_fail = should_fail
        if error_message:
            self._error_message = error_message

    def set_healthy(self, is_healthy: bool) -> None:
        """Set the health status for health_check.

        Args:
            is_healthy: Whether the system should report as healthy.
        """
        self._is_healthy = is_healthy

    def _fen_to_pieces(self, fen: str) -> dict[str, str]:
        """Convert FEN to piece mapping.

        Args:
            fen: Valid FEN string.

        Returns:
            Dictionary mapping square names to piece symbols.
            e.g., {"a1": "R", "e2": "P", "e8": "k"}
        """
        board = chess.Board(fen)
        pieces = {}

        for square in chess.SQUARES:
            piece = board.piece_at(square)
            if piece:
                square_name = chess.square_name(square)
                pieces[square_name] = piece.symbol()

        return pieces

    async def capture(self) -> DetectionResult:
        """Simulate board state capture.

        Returns:
            DetectionResult with current FEN and piece positions.
        """
        # Simulate capture delay
        if self._capture_delay > 0:
            await asyncio.sleep(self._capture_delay)

        if self._should_fail:
            return DetectionResult(
                success=False,
                fen=None,
                pieces=None,
                error=self._error_message,
            )

        pieces = self._fen_to_pieces(self._current_fen)

        return DetectionResult(
            success=True,
            fen=self._current_fen,
            pieces=pieces,
            error=None,
        )

    async def health_check(self) -> bool:
        """Check mock system health.

        Returns:
            Current health status.
        """
        return self._is_healthy
