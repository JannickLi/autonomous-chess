"""ROS-based detection client for board state capture.

This client communicates with the detection module via ROS topics:
- Publishes to /capture to trigger detection
- Subscribes to /position to receive board state
"""

import logging
from typing import Any

from backend.external.interfaces import DetectionClient, DetectionResult
from backend.external.ros.bridge import ROSBridgeBase, ROSMessage

logger = logging.getLogger(__name__)

# Default topic names (can be remapped via configuration)
DEFAULT_CAPTURE_TOPIC = "/capture"
DEFAULT_POSITION_TOPIC = "/position"
DEFAULT_STATUS_TOPIC = "/detection_status"


class ROSDetectionClient(DetectionClient):
    """Detection client that communicates via ROS topics.

    Topics:
        /capture (pub): Trigger board detection (std_msgs/Empty equivalent)
        /position (sub): Receive board position (chess_msgs/BoardPosition)
        /detection_status (sub): Detection system health status
    """

    def __init__(
        self,
        bridge: ROSBridgeBase,
        capture_topic: str = DEFAULT_CAPTURE_TOPIC,
        position_topic: str = DEFAULT_POSITION_TOPIC,
        status_topic: str = DEFAULT_STATUS_TOPIC,
        capture_timeout: float = 10.0,
    ) -> None:
        """Initialize the ROS detection client.

        Args:
            bridge: The ROS bridge to use for communication.
            capture_topic: Topic to publish capture triggers.
            position_topic: Topic to receive position data.
            status_topic: Topic to receive health status.
            capture_timeout: Timeout in seconds for capture response.
        """
        self._bridge = bridge
        self._capture_topic = capture_topic
        self._position_topic = position_topic
        self._status_topic = status_topic
        self._capture_timeout = capture_timeout

        # Latest status from detection module
        self._last_status: dict[str, Any] | None = None

        # Subscribe to status updates
        self._bridge.subscribe(status_topic, self._on_status_update)
        logger.info(
            f"ROSDetectionClient initialized: "
            f"capture={capture_topic}, position={position_topic}"
        )

    def _on_status_update(self, message: ROSMessage) -> None:
        """Handle detection status updates."""
        self._last_status = message.data
        logger.debug(f"Detection status update: {message.data}")

    async def capture(self) -> DetectionResult:
        """Request board state capture via ROS.

        Publishes to /capture topic and waits for response on /position.

        Returns:
            DetectionResult with board state or error.
        """
        logger.info("Requesting board capture via ROS")

        # Publish capture trigger
        await self._bridge.publish(self._capture_topic, {})

        # Wait for position response
        message = await self._bridge.wait_for_message(
            self._position_topic, timeout=self._capture_timeout
        )

        if message is None:
            logger.error("Timeout waiting for position from detection module")
            return DetectionResult(
                success=False,
                error=f"Timeout waiting for detection response ({self._capture_timeout}s)",
            )

        return self._parse_position_message(message)

    def _parse_position_message(self, message: ROSMessage) -> DetectionResult:
        """Parse a BoardPosition message into DetectionResult.

        Expected message.data structure (from chess_msgs/BoardPosition):
        {
            "success": bool,
            "fen": str,
            "squares": ["a1", "a2", ..., "h8"],
            "pieces": ["R", "", "P", ...],  # piece at each square
            "error": str,
            "confidence": float
        }
        """
        data = message.data

        # Check for success flag
        if not data.get("success", False):
            return DetectionResult(
                success=False,
                error=data.get("error", "Detection failed"),
            )

        # Extract FEN and normalize to full 6-field format
        fen = data.get("fen")
        if not fen:
            return DetectionResult(
                success=False,
                error="No FEN in detection response",
            )
        # If FEN only has the piece placement (no turn/castling fields), add defaults
        fen_parts = fen.split()
        if len(fen_parts) == 1:
            fen = f"{fen_parts[0]} w - - 0 1"
        elif len(fen_parts) < 6:
            defaults = ["w", "-", "-", "0", "1"]
            fen = " ".join(fen_parts + defaults[len(fen_parts) - 1:])

        # Build pieces dictionary from squares/pieces arrays
        pieces: dict[str, str] | None = None
        squares = data.get("squares", [])
        piece_list = data.get("pieces", [])

        if squares and piece_list and len(squares) == len(piece_list):
            pieces = {}
            for square, piece in zip(squares, piece_list):
                if piece:  # Only include non-empty squares
                    pieces[square] = piece

        confidence = data.get("confidence", 1.0)
        logger.info(
            f"Detection successful: FEN={fen[:20]}..., confidence={confidence:.2f}"
        )

        return DetectionResult(
            success=True,
            fen=fen,
            pieces=pieces,
        )

    async def health_check(self) -> bool:
        """Check if the detection system is healthy.

        Returns:
            True if detection module is connected and ready.
        """
        # Check if bridge is connected
        if not await self._bridge.is_connected():
            return False

        # Check last known status
        if self._last_status is not None:
            return (
                self._last_status.get("camera_connected", False)
                and self._last_status.get("is_ready", False)
            )

        # If no status received yet, assume healthy if bridge is connected
        return True

    def get_last_status(self) -> dict[str, Any] | None:
        """Get the last received detection status.

        Returns:
            Last status dict or None if no status received.
        """
        return self._last_status
