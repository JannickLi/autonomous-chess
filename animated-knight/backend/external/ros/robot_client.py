"""ROS-based robot client for move execution.

This client communicates with the robot engine via ROS topics:
- Publishes to /move to send move commands
- Publishes to /robot_home to send robot to home position
- Subscribes to /move_result to receive execution results
- Subscribes to /robot_status for health monitoring
"""

import logging
from typing import Any

from backend.external.interfaces import MoveCommand, RobotClient, RobotResult
from backend.external.ros.bridge import ROSBridgeBase, ROSMessage

logger = logging.getLogger(__name__)

# Default topic names (can be remapped via configuration)
DEFAULT_MOVE_TOPIC = "/move"
DEFAULT_MOVE_RESULT_TOPIC = "/move_result"
DEFAULT_ROBOT_HOME_TOPIC = "/robot_home"
DEFAULT_ROBOT_STATUS_TOPIC = "/robot_status"


class ROSRobotClient(RobotClient):
    """Robot client that communicates via ROS topics.

    Topics:
        /move (pub): Send move commands (chess_msgs/MoveCommand)
        /move_result (sub): Receive execution results (chess_msgs/MoveResult)
        /robot_home (pub): Send robot to home position (std_msgs/Empty)
        /robot_status (sub): Robot health status (chess_msgs/RobotStatus)
    """

    def __init__(
        self,
        bridge: ROSBridgeBase,
        move_topic: str = DEFAULT_MOVE_TOPIC,
        move_result_topic: str = DEFAULT_MOVE_RESULT_TOPIC,
        robot_home_topic: str = DEFAULT_ROBOT_HOME_TOPIC,
        robot_status_topic: str = DEFAULT_ROBOT_STATUS_TOPIC,
        move_timeout: float = 60.0,
        home_timeout: float = 30.0,
    ) -> None:
        """Initialize the ROS robot client.

        Args:
            bridge: The ROS bridge to use for communication.
            move_topic: Topic to publish move commands.
            move_result_topic: Topic to receive move results.
            robot_home_topic: Topic to publish home commands.
            robot_status_topic: Topic to receive robot status.
            move_timeout: Timeout in seconds for move execution.
            home_timeout: Timeout in seconds for home command.
        """
        self._bridge = bridge
        self._move_topic = move_topic
        self._move_result_topic = move_result_topic
        self._robot_home_topic = robot_home_topic
        self._robot_status_topic = robot_status_topic
        self._move_timeout = move_timeout
        self._home_timeout = home_timeout

        # Latest status from robot
        self._last_status: dict[str, Any] | None = None

        # Subscribe to status updates
        self._bridge.subscribe(robot_status_topic, self._on_status_update)
        logger.info(
            f"ROSRobotClient initialized: "
            f"move={move_topic}, result={move_result_topic}"
        )

    def _on_status_update(self, message: ROSMessage) -> None:
        """Handle robot status updates."""
        self._last_status = message.data
        logger.debug(f"Robot status update: {message.data}")

    async def execute_move(self, command: MoveCommand) -> RobotResult:
        """Execute a chess move via ROS.

        Publishes MoveCommand to /move topic and waits for result on /move_result.

        Args:
            command: The move command to execute.

        Returns:
            RobotResult indicating success or failure.
        """
        logger.info(f"Executing move via ROS: {command.move}")

        # Convert MoveCommand to ROS message format
        move_message = self._command_to_message(command)

        # Publish move command
        await self._bridge.publish(self._move_topic, move_message)

        # Wait for result
        result_message = await self._bridge.wait_for_message(
            self._move_result_topic, timeout=self._move_timeout
        )

        if result_message is None:
            logger.error("Timeout waiting for move result from robot")
            return RobotResult(
                success=False,
                error=f"Timeout waiting for robot response ({self._move_timeout}s)",
            )

        return self._parse_result_message(result_message, command.move)

    def _command_to_message(self, command: MoveCommand) -> dict[str, Any]:
        """Convert MoveCommand to ROS message dictionary.

        Maps to chess_msgs/MoveCommand message format.
        """
        return {
            "move_uci": command.move,
            "from_square": command.from_square,
            "to_square": command.to_square,
            "piece_type": command.piece_type,
            "piece_color": command.piece_color,
            "is_capture": command.is_capture,
            "captured_piece": command.captured_piece or "",
            "is_castling": command.is_castling,
            "castling_type": self._get_castling_type(command),
            "is_en_passant": command.is_en_passant,
            "is_promotion": command.is_promotion,
            "promotion_piece": command.promotion_piece or "",
            "board_fen": command.board_fen,
        }

    def _get_castling_type(self, command: MoveCommand) -> str:
        """Determine castling type from move command."""
        if not command.is_castling:
            return ""

        # Kingside castling: king moves from e to g file
        if command.to_square[0] == "g":
            return "kingside"
        # Queenside castling: king moves from e to c file
        elif command.to_square[0] == "c":
            return "queenside"
        return ""

    def _parse_result_message(
        self, message: ROSMessage, expected_move: str
    ) -> RobotResult:
        """Parse a MoveResult message into RobotResult.

        Expected message.data structure (from chess_msgs/MoveResult):
        {
            "move_uci": str,
            "success": bool,
            "error": str,
            "execution_time": float
        }
        """
        data = message.data

        # Verify this is the result for our move
        result_move = data.get("move_uci", "")
        if result_move and result_move != expected_move:
            logger.warning(
                f"Move mismatch: expected {expected_move}, got {result_move}"
            )

        success = data.get("success", False)
        error = data.get("error")
        execution_time = data.get("execution_time", 0.0)

        if success:
            logger.info(
                f"Move {expected_move} executed successfully in {execution_time:.2f}s"
            )
        else:
            logger.error(f"Move {expected_move} failed: {error}")

        return RobotResult(
            success=success,
            error=error if not success else None,
        )

    async def health_check(self) -> bool:
        """Check if the robot system is healthy.

        Returns:
            True if robot is connected and ready.
        """
        # Check if bridge is connected
        if not await self._bridge.is_connected():
            return False

        # Check last known status
        if self._last_status is not None:
            state = self._last_status.get("state", "")
            is_ready = self._last_status.get("is_ready", False)
            # Robot is healthy if it's ready and not in error state
            return is_ready and state != "error"

        # If no status received yet, assume healthy if bridge is connected
        return True

    async def home(self) -> RobotResult:
        """Send robot to home position via ROS.

        Publishes to /robot_home topic and waits for status update.

        Returns:
            RobotResult indicating success or failure.
        """
        logger.info("Sending robot to home position via ROS")

        # Publish home command (empty message)
        await self._bridge.publish(self._robot_home_topic, {})

        # Wait for result - robot should publish a move_result for home operation
        result_message = await self._bridge.wait_for_message(
            self._move_result_topic, timeout=self._home_timeout
        )

        if result_message is None:
            # If no explicit result, check status
            if self._last_status and self._last_status.get("state") == "idle":
                return RobotResult(success=True)

            logger.warning("No confirmation for home command, assuming success")
            return RobotResult(success=True)

        data = result_message.data
        return RobotResult(
            success=data.get("success", True),
            error=data.get("error"),
        )

    def get_last_status(self) -> dict[str, Any] | None:
        """Get the last received robot status.

        Returns:
            Last status dict or None if no status received.
        """
        return self._last_status

    def is_robot_busy(self) -> bool:
        """Check if robot is currently executing a move.

        Returns:
            True if robot is busy, False if idle or unknown.
        """
        if self._last_status is None:
            return False
        return self._last_status.get("state") in ("moving", "homing", "calibrating")
