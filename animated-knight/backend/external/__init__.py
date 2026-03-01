"""External API integrations for camera detection and robot control."""

from .interfaces import (
    DetectionClient,
    DetectionResult,
    MoveCommand,
    RobotClient,
    RobotResult,
)
from .manager import ExternalServicesManager, get_external_manager

__all__ = [
    "DetectionClient",
    "DetectionResult",
    "MoveCommand",
    "RobotClient",
    "RobotResult",
    "ExternalServicesManager",
    "get_external_manager",
]
