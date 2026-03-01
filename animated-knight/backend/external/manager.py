"""External services manager for mode switching and client management."""

import logging
from functools import lru_cache
from typing import Literal

from backend.external.detection.mock_client import MockDetectionClient
from backend.external.interfaces import DetectionClient, RobotClient
from backend.external.robot.mock_client import MockRobotClient

logger = logging.getLogger(__name__)

OperationMode = Literal["simulation", "ros"]


class ExternalServicesManager:
    """Manager for external detection and robot services.

    Handles mode switching between simulation and ROS,
    and provides access to the appropriate client implementations.

    Modes:
        - simulation: Uses mock clients for development/testing without hardware
        - ros: Uses ROS topics for communication via TCP bridge
    """

    def __init__(
        self,
        operation_mode: OperationMode = "simulation",
        ros_config: dict | None = None,
    ):
        """Initialize the external services manager.

        Args:
            operation_mode: Initial operation mode ("simulation" or "ros").
            ros_config: ROS topic configuration (if operation_mode is "ros").
        """
        self._operation_mode = operation_mode
        self._ros_config = ros_config or {}

        # Initialize mock clients (always available for simulation)
        self._mock_detection = MockDetectionClient()
        self._mock_robot = MockRobotClient()

        # ROS clients will be initialized when ros mode is enabled
        self._ros_detection: DetectionClient | None = None
        self._ros_robot: RobotClient | None = None
        self._ros_bridge = None
        self._agent_listener = None

        # Initialize ROS clients if in ros mode
        if operation_mode == "ros":
            self._init_ros_clients()

    def _init_ros_clients(self) -> None:
        """Initialize ROS clients with the configured bridge."""
        try:
            from backend.external.ros.bridge import get_ros_bridge
            from backend.external.ros.detection_client import ROSDetectionClient
            from backend.external.ros.robot_client import ROSRobotClient

            # Get or create the ROS bridge
            self._ros_bridge = get_ros_bridge()

            # Create ROS clients with configured topics
            self._ros_detection = ROSDetectionClient(
                bridge=self._ros_bridge,
                capture_topic=self._ros_config.get("capture_topic", "/capture"),
                position_topic=self._ros_config.get("position_topic", "/position"),
                status_topic=self._ros_config.get("detection_status_topic", "/detection_status"),
                capture_timeout=self._ros_config.get("detection_timeout", 10.0),
            )

            self._ros_robot = ROSRobotClient(
                bridge=self._ros_bridge,
                move_topic=self._ros_config.get("move_topic", "/move"),
                move_result_topic=self._ros_config.get("move_result_topic", "/move_result"),
                robot_home_topic=self._ros_config.get("robot_home_topic", "/robot_home"),
                robot_status_topic=self._ros_config.get("robot_status_topic", "/robot_status"),
                move_timeout=self._ros_config.get("move_timeout", 60.0),
            )

            # Create agent listener (listens for move requests via ROS)
            from backend.external.ros.agent_listener import ROSAgentListener

            self._agent_listener = ROSAgentListener(
                bridge=self._ros_bridge,
                request_topic=self._ros_config.get("agent_request_topic", "/chess/agent_request"),
                opinions_topic=self._ros_config.get("agent_opinions_topic", "/chess/agent_opinions"),
            )

            logger.info("ROS clients initialized successfully")
        except ImportError as e:
            logger.warning(f"Failed to import ROS modules: {e}")
            logger.info("Falling back to simulation mode")
            self._operation_mode = "simulation"
        except Exception as e:
            logger.error(f"Failed to initialize ROS clients: {e}")
            logger.info("Falling back to simulation mode")
            self._operation_mode = "simulation"

    @property
    def operation_mode(self) -> OperationMode:
        """Get the current operation mode."""
        return self._operation_mode

    def set_operation_mode(self, mode: OperationMode) -> None:
        """Set the operation mode.

        Args:
            mode: The new operation mode ("simulation" or "ros").

        Raises:
            ValueError: If mode is not valid.
        """
        if mode not in ("simulation", "ros"):
            raise ValueError(f"Invalid operation mode: {mode}")

        # Initialize ROS clients if switching to ros mode
        if mode == "ros" and self._ros_bridge is None:
            self._init_ros_clients()
            # Check if init fell back to simulation
            if self._operation_mode == "simulation":
                logger.warning("ROS initialization failed, staying in simulation mode")
                return

        self._operation_mode = mode
        logger.info(f"Operation mode set to: {mode}")

    @property
    def detection_client(self) -> DetectionClient:
        """Get the appropriate detection client based on current mode.

        Returns:
            The detection client (mock or ROS).
        """
        if self._operation_mode == "ros" and self._ros_detection:
            return self._ros_detection
        return self._mock_detection

    @property
    def robot_client(self) -> RobotClient:
        """Get the appropriate robot client based on current mode.

        Returns:
            The robot client (mock or ROS).
        """
        if self._operation_mode == "ros" and self._ros_robot:
            return self._ros_robot
        return self._mock_robot

    @property
    def mock_detection(self) -> MockDetectionClient:
        """Get the mock detection client directly (for configuration).

        Returns:
            The mock detection client.
        """
        return self._mock_detection

    @property
    def mock_robot(self) -> MockRobotClient:
        """Get the mock robot client directly (for configuration).

        Returns:
            The mock robot client.
        """
        return self._mock_robot

    async def get_status(self) -> dict:
        """Get the status of all external services.

        Returns:
            Dictionary with service status information.
        """
        detection_healthy = await self.detection_client.health_check()
        robot_healthy = await self.robot_client.health_check()

        # Determine detection type
        detection_type = "ros" if (self._operation_mode == "ros" and self._ros_detection) else "mock"
        robot_type = "ros" if (self._operation_mode == "ros" and self._ros_robot) else "mock"

        return {
            "operation_mode": self._operation_mode,
            "detection": {
                "type": detection_type,
                "healthy": detection_healthy,
                "ros_topics": {
                    "capture": self._ros_config.get("capture_topic", "/capture"),
                    "position": self._ros_config.get("position_topic", "/position"),
                } if self._operation_mode == "ros" else None,
            },
            "robot": {
                "type": robot_type,
                "healthy": robot_healthy,
                "ros_topics": {
                    "move": self._ros_config.get("move_topic", "/move"),
                    "move_result": self._ros_config.get("move_result_topic", "/move_result"),
                } if self._operation_mode == "ros" else None,
            },
        }

    def is_ros_mode_available(self) -> bool:
        """Check if ROS mode can be enabled.

        Returns:
            True if ROS clients are initialized.
        """
        return self._ros_detection is not None and self._ros_robot is not None


# Global singleton instance
_manager: ExternalServicesManager | None = None


def get_external_manager() -> ExternalServicesManager:
    """Get the global external services manager instance.

    Returns:
        The singleton ExternalServicesManager.
    """
    global _manager
    if _manager is None:
        # Import here to avoid circular imports
        from backend.core.config import get_settings

        settings = get_settings()

        # Build ROS config from settings
        ros_config = {
            "capture_topic": settings.ros_capture_topic,
            "position_topic": settings.ros_position_topic,
            "move_topic": settings.ros_move_topic,
            "move_result_topic": settings.ros_move_result_topic,
            "robot_home_topic": settings.ros_robot_home_topic,
            "robot_status_topic": settings.ros_robot_status_topic,
            "detection_status_topic": settings.ros_detection_status_topic,
            "cam_topic": settings.ros_cam_topic,
            "detection_timeout": settings.ros_detection_timeout,
            "move_timeout": settings.ros_move_timeout,
            "agent_request_topic": settings.ros_agent_request_topic,
            "agent_opinions_topic": settings.ros_agent_opinions_topic,
        }

        _manager = ExternalServicesManager(
            operation_mode=settings.operation_mode,
            ros_config=ros_config,
        )
    return _manager


def reset_external_manager() -> None:
    """Reset the global manager (useful for testing)."""
    global _manager
    _manager = None
