"""Mock robot client for development and testing."""

import asyncio
from dataclasses import dataclass
from datetime import datetime

from backend.external.interfaces import MoveCommand, RobotClient, RobotResult


@dataclass
class MoveRecord:
    """Record of a move executed by the mock robot."""

    command: MoveCommand
    timestamp: datetime
    success: bool
    error: str | None = None


class MockRobotClient(RobotClient):
    """Mock implementation of the robot client for testing.

    Accepts move commands, logs them, and simulates execution delay.
    """

    def __init__(
        self,
        execution_delay: float = 1.0,
        should_fail: bool = False,
        error_message: str = "Robot execution failed",
    ):
        """Initialize the mock robot client.

        Args:
            execution_delay: Simulated delay in seconds for move execution.
            should_fail: If True, execute_move will return an error.
            error_message: Error message to return when should_fail is True.
        """
        self._execution_delay = execution_delay
        self._should_fail = should_fail
        self._error_message = error_message
        self._is_healthy = True
        self._is_homed = False
        self._move_history: list[MoveRecord] = []

    def set_should_fail(self, should_fail: bool, error_message: str | None = None) -> None:
        """Configure whether execute_move should fail.

        Args:
            should_fail: If True, next execution will fail.
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

    def get_move_history(self) -> list[MoveRecord]:
        """Get the history of executed moves.

        Returns:
            List of MoveRecord objects.
        """
        return self._move_history.copy()

    def clear_history(self) -> None:
        """Clear the move history."""
        self._move_history.clear()

    def get_last_move(self) -> MoveRecord | None:
        """Get the most recent move.

        Returns:
            The last MoveRecord or None if no moves executed.
        """
        return self._move_history[-1] if self._move_history else None

    async def execute_move(self, command: MoveCommand) -> RobotResult:
        """Simulate move execution.

        Args:
            command: The move command to execute.

        Returns:
            RobotResult indicating success or failure.
        """
        # Simulate execution delay
        if self._execution_delay > 0:
            await asyncio.sleep(self._execution_delay)

        if self._should_fail:
            record = MoveRecord(
                command=command,
                timestamp=datetime.now(),
                success=False,
                error=self._error_message,
            )
            self._move_history.append(record)
            return RobotResult(success=False, error=self._error_message)

        record = MoveRecord(
            command=command,
            timestamp=datetime.now(),
            success=True,
        )
        self._move_history.append(record)

        return RobotResult(success=True)

    async def health_check(self) -> bool:
        """Check mock system health.

        Returns:
            Current health status.
        """
        return self._is_healthy

    async def home(self) -> RobotResult:
        """Simulate returning to home position.

        Returns:
            RobotResult indicating success or failure.
        """
        if self._execution_delay > 0:
            await asyncio.sleep(self._execution_delay / 2)

        if self._should_fail:
            return RobotResult(success=False, error=self._error_message)

        self._is_homed = True
        return RobotResult(success=True)

    @property
    def is_homed(self) -> bool:
        """Check if robot has been homed.

        Returns:
            True if home() was called successfully.
        """
        return self._is_homed
