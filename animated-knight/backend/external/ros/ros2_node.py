"""ROS2 Node implementation for chess-agents.

This module provides the actual ROS2 node implementation that handles
communication with the perception and robot control nodes via ROS2 topics.

Usage:
    source /opt/ros/humble/setup.bash
    source chess_msgs/install/setup.bash
    # Then start the backend with OPERATION_MODE=ros
"""

import asyncio
import logging
import threading
import time
from queue import Empty, Queue
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Import ROS2 dependencies
try:
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import QoSProfile, QoSHistoryPolicy, QoSDurabilityPolicy
    from std_msgs.msg import Empty as EmptyMsg

    ROS2_AVAILABLE = True
except ImportError:
    ROS2_AVAILABLE = False
    logger.warning("rclpy not available - ROS2 node cannot be used")

# Import custom chess messages
try:
    from chess_msgs.msg import BoardState, MoveCommand, MoveResult

    CHESS_MSGS_AVAILABLE = True
except ImportError:
    CHESS_MSGS_AVAILABLE = False
    logger.warning("chess_msgs not available - build the package first")


class ChessAgentROS2Node:
    """ROS2 node wrapper for the chess-agents backend.

    This class manages a ROS2 node in a background thread and provides
    async methods for publishing and subscribing to chess-related topics.
    """

    def __init__(self, node_name: str = "chess_agent_node"):
        """Initialize the ROS2 node.

        Args:
            node_name: Name for the ROS2 node.

        Raises:
            RuntimeError: If ROS2 or chess_msgs are not available.
        """
        if not ROS2_AVAILABLE:
            raise RuntimeError("rclpy is not available - ensure ROS2 is sourced")
        if not CHESS_MSGS_AVAILABLE:
            raise RuntimeError("chess_msgs not available - build the package first")

        self._node_name = node_name
        self._node: Node | None = None
        self._spin_thread: threading.Thread | None = None
        self._shutdown_flag = threading.Event()

        # Message queues for async waiting
        self._message_queues: dict[str, Queue] = {}
        self._queue_lock = threading.Lock()

        # Subscriber callbacks
        self._callbacks: dict[str, list[Callable]] = {}

        # Publishers (created lazily)
        self._publishers: dict[str, Any] = {}

        # Subscribers (created lazily)
        self._subscribers: dict[str, Any] = {}

        # Initialize ROS2
        self._initialize_ros2()

    def _initialize_ros2(self) -> None:
        """Initialize the ROS2 context and node."""
        if not rclpy.ok():
            rclpy.init()

        self._node = rclpy.create_node(self._node_name)
        logger.info(f"ROS2 node '{self._node_name}' created")

        # Create publishers for outgoing messages
        self._create_publishers()

        # Create subscribers for incoming messages
        self._create_subscribers()

        # Start spin thread
        self._spin_thread = threading.Thread(target=self._spin_loop, daemon=True)
        self._spin_thread.start()

    def _create_publishers(self) -> None:
        """Create all required publishers."""
        # Capture trigger (Empty message)
        self._publishers["/chess/capture"] = self._node.create_publisher(
            EmptyMsg, "/chess/capture", 10
        )

        # Move command
        self._publishers["/chess/move_request"] = self._node.create_publisher(
            MoveCommand, "/chess/move_request", 10
        )

        # Robot home command (Empty message)
        self._publishers["/chess/robot/home"] = self._node.create_publisher(
            EmptyMsg, "/chess/robot/home", 10
        )

        logger.debug("ROS2 publishers created")

    def _create_subscribers(self) -> None:
        """Create all required subscribers."""
        # QoS for volatile messages
        volatile_qos = QoSProfile(
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=10,
            durability=QoSDurabilityPolicy.VOLATILE,
        )

        # Board state subscriber
        self._subscribers["/chess/perception_result"] = self._node.create_subscription(
            BoardState,
            "/chess/perception_result",
            lambda msg: self._on_message("/chess/perception_result", msg),
            volatile_qos,
        )

        # Move result subscriber
        self._subscribers["/chess/move_result"] = self._node.create_subscription(
            MoveResult,
            "/chess/move_result",
            lambda msg: self._on_message("/chess/move_result", msg),
            volatile_qos,
        )

        logger.debug("ROS2 subscribers created")

    def _spin_loop(self) -> None:
        """Background thread that spins the ROS2 node."""
        while not self._shutdown_flag.is_set() and rclpy.ok():
            try:
                rclpy.spin_once(self._node, timeout_sec=0.1)
            except Exception as e:
                if not self._shutdown_flag.is_set():
                    logger.error(f"Error in ROS2 spin loop: {e}")
                break

    def _on_message(self, topic: str, msg: Any) -> None:
        """Handle incoming ROS2 message."""
        # Convert to dict for consistent interface
        data = self._message_to_dict(topic, msg)

        # Add to queue for wait_for_message
        with self._queue_lock:
            if topic not in self._message_queues:
                self._message_queues[topic] = Queue()
            self._message_queues[topic].put(data)

        # Call registered callbacks
        if topic in self._callbacks:
            for callback in self._callbacks[topic]:
                try:
                    callback(data)
                except Exception as e:
                    logger.error(f"Error in callback for {topic}: {e}")

        logger.debug(f"Received message on {topic}")

    def _message_to_dict(self, topic: str, msg: Any) -> dict[str, Any]:
        """Convert a ROS2 message to a dictionary."""
        if topic == "/chess/perception_result":
            return {
                "success": msg.success,
                "fen": msg.fen,
                "squares": list(msg.squares),
                "pieces": list(msg.pieces),
                "confidence": msg.confidence,
                "error": msg.error,
                "timestamp": time.time(),
            }
        elif topic == "/chess/move_result":
            return {
                "move_uci": msg.move_uci,
                "success": msg.success,
                "error": msg.error,
                "execution_time": msg.execution_time_sec,
                "timestamp": time.time(),
            }
        else:
            # Generic fallback
            return {"raw": str(msg), "timestamp": time.time()}

    async def publish_capture_request(self) -> None:
        """Publish a board capture request."""
        if "/chess/capture" not in self._publishers:
            raise RuntimeError("Capture publisher not initialized")

        msg = EmptyMsg()
        self._publishers["/chess/capture"].publish(msg)
        logger.debug("Published capture request")

    async def publish_move_command(self, command: dict[str, Any]) -> None:
        """Publish a move command.

        Args:
            command: Dictionary with move command fields.
        """
        if "/chess/move_request" not in self._publishers:
            raise RuntimeError("Move command publisher not initialized")

        msg = MoveCommand()
        msg.header.stamp = self._node.get_clock().now().to_msg()
        msg.move_uci = command.get("move_uci", "")
        msg.from_square = command.get("from_square", "")
        msg.to_square = command.get("to_square", "")
        msg.piece_type = command.get("piece_type", "")
        msg.piece_color = command.get("piece_color", "")
        msg.is_capture = command.get("is_capture", False)
        msg.captured_piece = command.get("captured_piece", "")
        msg.is_castling = command.get("is_castling", False)
        msg.castling_type = command.get("castling_type", "")
        msg.is_en_passant = command.get("is_en_passant", False)
        msg.is_promotion = command.get("is_promotion", False)
        msg.promotion_piece = command.get("promotion_piece", "")
        msg.board_fen = command.get("board_fen", "")

        self._publishers["/chess/move_request"].publish(msg)
        logger.debug(f"Published move command: {msg.move_uci}")

    async def publish_home_command(self) -> None:
        """Publish a robot home command."""
        if "/chess/robot/home" not in self._publishers:
            raise RuntimeError("Home publisher not initialized")

        msg = EmptyMsg()
        self._publishers["/chess/robot/home"].publish(msg)
        logger.debug("Published home command")

    async def wait_for_message(
        self, topic: str, timeout: float = 10.0
    ) -> dict[str, Any] | None:
        """Wait for a message on a topic.

        Args:
            topic: The topic to wait on.
            timeout: Maximum time to wait in seconds.

        Returns:
            Message data as dict, or None if timeout.
        """
        with self._queue_lock:
            if topic not in self._message_queues:
                self._message_queues[topic] = Queue()
            queue = self._message_queues[topic]

        # Use asyncio-compatible waiting
        loop = asyncio.get_event_loop()
        try:
            message = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: queue.get(timeout=timeout)),
                timeout=timeout,
            )
            return message
        except (Empty, asyncio.TimeoutError):
            logger.warning(f"Timeout waiting for message on {topic}")
            return None

    def subscribe(self, topic: str, callback: Callable[[dict[str, Any]], None]) -> None:
        """Register a callback for a topic.

        Args:
            topic: The topic to subscribe to.
            callback: Function to call when message received.
        """
        if topic not in self._callbacks:
            self._callbacks[topic] = []
        self._callbacks[topic].append(callback)
        logger.debug(f"Registered callback for {topic}")

    def is_connected(self) -> bool:
        """Check if the ROS2 node is healthy."""
        return (
            self._node is not None
            and rclpy.ok()
            and not self._shutdown_flag.is_set()
        )

    def shutdown(self) -> None:
        """Shutdown the ROS2 node."""
        logger.info("Shutting down ROS2 node")
        self._shutdown_flag.set()

        if self._spin_thread and self._spin_thread.is_alive():
            self._spin_thread.join(timeout=2.0)

        if self._node:
            self._node.destroy_node()
            self._node = None

        # Don't shutdown rclpy globally as other nodes might be using it


# Global node instance
_ros2_node: ChessAgentROS2Node | None = None


def get_ros2_node() -> ChessAgentROS2Node:
    """Get or create the global ROS2 node instance.

    Returns:
        The ROS2 node instance.

    Raises:
        RuntimeError: If ROS2 is not available.
    """
    global _ros2_node

    if _ros2_node is None:
        _ros2_node = ChessAgentROS2Node()

    return _ros2_node


def reset_ros2_node() -> None:
    """Reset the global ROS2 node (useful for testing)."""
    global _ros2_node

    if _ros2_node is not None:
        _ros2_node.shutdown()
        _ros2_node = None
