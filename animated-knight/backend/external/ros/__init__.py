"""ROS integration for external hardware communication.

This module provides ROS-based clients for the detection and robot systems.
When ROS is not available, it falls back to mock implementations.
"""

from backend.external.ros.bridge import ROSBridgeBase, get_ros_bridge
from backend.external.ros.detection_client import ROSDetectionClient
from backend.external.ros.robot_client import ROSRobotClient

__all__ = [
    "ROSBridgeBase",
    "ROSDetectionClient",
    "ROSRobotClient",
    "get_ros_bridge",
]
