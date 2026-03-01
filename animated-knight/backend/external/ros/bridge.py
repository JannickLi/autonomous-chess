"""ROS Bridge for communication with detection and robot systems.

This module provides an abstraction layer for ROS communication that:
1. Works with actual ROS when available
2. Falls back to mock behavior when ROS is not installed
3. Supports both ROS 1 (rospy) and ROS 2 (rclpy)
"""

import asyncio
import logging
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from queue import Empty, Queue
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Try to import ROS - will be None if not available
try:
    import rospy
    from std_msgs.msg import Empty as ROSEmpty

    ROS_VERSION = 1
    ROS_AVAILABLE = True
    logger.info("ROS 1 (rospy) detected")
except ImportError:
    rospy = None
    ROSEmpty = None
    ROS_VERSION = None
    ROS_AVAILABLE = False

# Try ROS 2 if ROS 1 not available
if not ROS_AVAILABLE:
    try:
        import rclpy
        from rclpy.node import Node
        from std_msgs.msg import Empty as ROS2Empty

        ROS_VERSION = 2
        ROS_AVAILABLE = True
        ROSEmpty = ROS2Empty
        logger.info("ROS 2 (rclpy) detected")
    except ImportError:
        rclpy = None
        ROS_VERSION = None
        logger.info("ROS not available - using mock bridge")


@dataclass
class ROSMessage:
    """Generic ROS message container for cross-version compatibility."""

    topic: str
    data: dict[str, Any]
    timestamp: float = field(default_factory=lambda: 0.0)


class ROSBridgeBase(ABC):
    """Abstract base class for ROS bridge implementations."""

    @abstractmethod
    async def publish(self, topic: str, message: dict[str, Any]) -> None:
        """Publish a message to a topic."""
        ...

    @abstractmethod
    async def wait_for_message(
        self, topic: str, timeout: float = 10.0
    ) -> ROSMessage | None:
        """Wait for a message on a topic."""
        ...

    @abstractmethod
    def subscribe(
        self, topic: str, callback: Callable[[ROSMessage], None]
    ) -> None:
        """Subscribe to a topic with a callback."""
        ...

    @abstractmethod
    async def is_connected(self) -> bool:
        """Check if ROS is connected and healthy."""
        ...

    @abstractmethod
    def shutdown(self) -> None:
        """Shutdown the ROS bridge."""
        ...


class MockROSBridge(ROSBridgeBase):
    """Mock ROS bridge for simulation mode without ROS installed.

    This allows the chess module to run in simulation mode on systems
    without ROS, useful for development and testing.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, list[Callable[[ROSMessage], None]]] = {}
        self._message_queues: dict[str, Queue[ROSMessage]] = {}
        self._published_messages: list[ROSMessage] = []
        self._simulated_responses: dict[str, ROSMessage] = {}
        logger.info("MockROSBridge initialized (simulation mode)")

    async def publish(self, topic: str, message: dict[str, Any]) -> None:
        """Publish a message (stored for inspection in tests)."""
        import time

        ros_message = ROSMessage(topic=topic, data=message, timestamp=time.time())
        self._published_messages.append(ros_message)
        logger.debug(f"MockROS published to {topic}: {message}")

        # If there's a simulated response configured, trigger it
        if topic in self._simulated_responses:
            response = self._simulated_responses[topic]
            await self._deliver_message(response)

    async def wait_for_message(
        self, topic: str, timeout: float = 10.0
    ) -> ROSMessage | None:
        """Wait for a message on a topic."""
        if topic not in self._message_queues:
            self._message_queues[topic] = Queue()

        try:
            # Use asyncio-compatible waiting
            loop = asyncio.get_event_loop()
            message = await asyncio.wait_for(
                loop.run_in_executor(
                    None, lambda: self._message_queues[topic].get(timeout=timeout)
                ),
                timeout=timeout,
            )
            return message
        except (Empty, asyncio.TimeoutError):
            logger.warning(f"Timeout waiting for message on {topic}")
            return None

    def subscribe(
        self, topic: str, callback: Callable[[ROSMessage], None]
    ) -> None:
        """Subscribe to a topic with a callback."""
        if topic not in self._subscribers:
            self._subscribers[topic] = []
            self._message_queues[topic] = Queue()
        self._subscribers[topic].append(callback)
        logger.debug(f"MockROS subscribed to {topic}")

    async def is_connected(self) -> bool:
        """Mock is always 'connected'."""
        return True

    def shutdown(self) -> None:
        """Shutdown the mock bridge."""
        self._subscribers.clear()
        self._message_queues.clear()
        logger.info("MockROSBridge shutdown")

    # Mock-specific methods for testing

    def set_simulated_response(
        self, trigger_topic: str, response_topic: str, response_data: dict[str, Any]
    ) -> None:
        """Configure an automatic response when a topic is published to.

        Args:
            trigger_topic: Topic that triggers the response when published to.
            response_topic: Topic to send the response on.
            response_data: Data to include in the response message.
        """
        import time

        self._simulated_responses[trigger_topic] = ROSMessage(
            topic=response_topic, data=response_data, timestamp=time.time()
        )

    async def simulate_message(self, topic: str, data: dict[str, Any]) -> None:
        """Simulate receiving a message on a topic.

        Args:
            topic: Topic to simulate message on.
            data: Message data.
        """
        import time

        message = ROSMessage(topic=topic, data=data, timestamp=time.time())
        await self._deliver_message(message)

    async def _deliver_message(self, message: ROSMessage) -> None:
        """Deliver a message to subscribers and queues."""
        topic = message.topic

        # Add to queue for wait_for_message
        if topic in self._message_queues:
            self._message_queues[topic].put(message)

        # Call subscribers
        if topic in self._subscribers:
            for callback in self._subscribers[topic]:
                callback(message)

    def get_published_messages(self, topic: str | None = None) -> list[ROSMessage]:
        """Get all published messages, optionally filtered by topic."""
        if topic is None:
            return self._published_messages.copy()
        return [m for m in self._published_messages if m.topic == topic]

    def clear_messages(self) -> None:
        """Clear all recorded messages."""
        self._published_messages.clear()


class ROS1Bridge(ROSBridgeBase):
    """ROS 1 bridge using rospy.

    NOTE: This is a stub implementation. The actual ROS integration
    will be implemented when the repositories are merged.
    """

    def __init__(self, node_name: str = "chess_agents") -> None:
        if not ROS_AVAILABLE or ROS_VERSION != 1:
            raise RuntimeError("ROS 1 (rospy) is not available")

        self._node_name = node_name
        self._publishers: dict[str, Any] = {}
        self._subscribers: dict[str, Any] = {}
        self._message_queues: dict[str, Queue[ROSMessage]] = {}
        self._spin_thread: threading.Thread | None = None
        self._shutdown_flag = threading.Event()

        # Initialize ROS node
        rospy.init_node(node_name, anonymous=True)
        logger.info(f"ROS1Bridge initialized with node name: {node_name}")

        # Start spin thread
        self._start_spin_thread()

    def _start_spin_thread(self) -> None:
        """Start the ROS spin thread."""

        def spin():
            rate = rospy.Rate(100)  # 100 Hz
            while not self._shutdown_flag.is_set() and not rospy.is_shutdown():
                rate.sleep()

        self._spin_thread = threading.Thread(target=spin, daemon=True)
        self._spin_thread.start()

    async def publish(self, topic: str, message: dict[str, Any]) -> None:
        """Publish a message to a topic."""
        # TODO: Implement actual ROS publishing with proper message types
        # This requires the chess_msgs package to be built
        raise NotImplementedError(
            "ROS 1 publishing not yet implemented. "
            "Requires chess_msgs package with custom message definitions."
        )

    async def wait_for_message(
        self, topic: str, timeout: float = 10.0
    ) -> ROSMessage | None:
        """Wait for a message on a topic."""
        # TODO: Implement actual ROS message waiting
        raise NotImplementedError(
            "ROS 1 message waiting not yet implemented. "
            "Requires chess_msgs package with custom message definitions."
        )

    def subscribe(
        self, topic: str, callback: Callable[[ROSMessage], None]
    ) -> None:
        """Subscribe to a topic with a callback."""
        # TODO: Implement actual ROS subscription
        raise NotImplementedError(
            "ROS 1 subscription not yet implemented. "
            "Requires chess_msgs package with custom message definitions."
        )

    async def is_connected(self) -> bool:
        """Check if ROS is connected."""
        return not rospy.is_shutdown()

    def shutdown(self) -> None:
        """Shutdown the ROS bridge."""
        self._shutdown_flag.set()
        if self._spin_thread:
            self._spin_thread.join(timeout=2.0)
        rospy.signal_shutdown("Chess agents shutdown")
        logger.info("ROS1Bridge shutdown")


class ROS2Bridge(ROSBridgeBase):
    """ROS 2 bridge using rclpy and the ChessAgentROS2Node.

    This bridge wraps the ChessAgentROS2Node to provide the ROSBridgeBase
    interface for the detection and robot clients.
    """

    def __init__(self, node_name: str = "chess_agents") -> None:
        if not ROS_AVAILABLE or ROS_VERSION != 2:
            raise RuntimeError("ROS 2 (rclpy) is not available")

        self._node_name = node_name

        # Import and initialize the ROS2 node
        try:
            from backend.external.ros.ros2_node import get_ros2_node

            self._ros2_node = get_ros2_node()
            logger.info(f"ROS2Bridge initialized with node: {node_name}")
        except Exception as e:
            raise RuntimeError(f"Failed to initialize ROS2 node: {e}") from e

    async def publish(self, topic: str, message: dict[str, Any]) -> None:
        """Publish a message to a ROS2 topic.

        Args:
            topic: The topic to publish to.
            message: The message data as a dictionary.
        """
        import time

        # Route to appropriate publish method based on topic
        if topic.endswith("/capture") or "capture" in topic:
            await self._ros2_node.publish_capture_request()
        elif topic.endswith("/move_request") or topic.endswith("/command") or ("move" in topic and "result" not in topic):
            await self._ros2_node.publish_move_command(message)
        elif topic.endswith("/home") or "home" in topic:
            await self._ros2_node.publish_home_command()
        else:
            logger.warning(f"Unknown topic for publish: {topic}")

        logger.debug(f"ROS2 published to {topic}: {message}")

    async def wait_for_message(
        self, topic: str, timeout: float = 10.0
    ) -> ROSMessage | None:
        """Wait for a message on a ROS2 topic.

        Args:
            topic: The topic to wait on.
            timeout: Maximum time to wait in seconds.

        Returns:
            ROSMessage containing the received data, or None on timeout.
        """
        import time

        data = await self._ros2_node.wait_for_message(topic, timeout)

        if data is None:
            return None

        return ROSMessage(
            topic=topic,
            data=data,
            timestamp=data.get("timestamp", time.time()),
        )

    def subscribe(
        self, topic: str, callback: Callable[[ROSMessage], None]
    ) -> None:
        """Subscribe to a ROS2 topic with a callback.

        Args:
            topic: The topic to subscribe to.
            callback: Function to call when message is received.
        """
        import time

        def wrapper(data: dict[str, Any]) -> None:
            ros_msg = ROSMessage(
                topic=topic,
                data=data,
                timestamp=data.get("timestamp", time.time()),
            )
            callback(ros_msg)

        self._ros2_node.subscribe(topic, wrapper)
        logger.debug(f"ROS2 subscribed to {topic}")

    async def is_connected(self) -> bool:
        """Check if the ROS2 node is connected and healthy.

        Returns:
            True if the node is running and connected.
        """
        return self._ros2_node.is_connected()

    def shutdown(self) -> None:
        """Shutdown the ROS2 bridge."""
        from backend.external.ros.ros2_node import reset_ros2_node

        reset_ros2_node()
        logger.info("ROS2Bridge shutdown")


# Global bridge instance
_bridge: ROSBridgeBase | None = None


def get_ros_bridge(force_mock: bool = False) -> ROSBridgeBase:
    """Get the global ROS bridge instance.

    Selection priority:
    1. MockROSBridge if force_mock=True
    2. TCPROSBridge if ROS_TCP_HOST is configured (no local ROS needed)
    3. ROS1Bridge / ROS2Bridge if rclpy/rospy is available locally
    4. MockROSBridge as fallback

    Args:
        force_mock: If True, always use MockROSBridge regardless of configuration.

    Returns:
        The appropriate ROS bridge implementation.
    """
    global _bridge

    if _bridge is not None:
        return _bridge

    if force_mock:
        _bridge = MockROSBridge()
        return _bridge

    # Check for TCP bridge configuration first
    try:
        from backend.core.config import get_settings
        settings = get_settings()
        if settings.ros_tcp_host:
            from backend.external.ros.tcp_bridge import TCPROSBridge
            _bridge = TCPROSBridge(
                host=settings.ros_tcp_host,
                port=settings.ros_tcp_port,
            )
            logger.info(
                f"Using TCPROSBridge → {settings.ros_tcp_host}:{settings.ros_tcp_port}"
            )
            return _bridge
    except Exception as e:
        logger.warning(f"TCP bridge configuration check failed: {e}")

    # Fall back to local ROS installation
    if not ROS_AVAILABLE:
        _bridge = MockROSBridge()
    elif ROS_VERSION == 1:
        try:
            _bridge = ROS1Bridge()
        except Exception as e:
            logger.warning(f"Failed to initialize ROS 1 bridge: {e}, using mock")
            _bridge = MockROSBridge()
    elif ROS_VERSION == 2:
        try:
            _bridge = ROS2Bridge()
        except Exception as e:
            logger.warning(f"Failed to initialize ROS 2 bridge: {e}, using mock")
            _bridge = MockROSBridge()
    else:
        _bridge = MockROSBridge()

    return _bridge


def reset_ros_bridge() -> None:
    """Reset the global ROS bridge (useful for testing)."""
    global _bridge
    if _bridge is not None:
        _bridge.shutdown()
    _bridge = None
