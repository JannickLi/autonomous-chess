"""External services API routes for camera detection and robot control."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.orchestration import get_orchestrator
from backend.external import get_external_manager

router = APIRouter(prefix="/api/external", tags=["external"])


class SetModeRequest(BaseModel):
    """Request to set the operation mode."""

    mode: str  # "simulation" or "ros"


class DetectionResponse(BaseModel):
    """Response from detection request."""

    success: bool
    fen: str | None = None
    pieces: dict[str, str] | None = None
    error: str | None = None


class RobotMoveRequest(BaseModel):
    """Request to send a move to the robot."""

    move: str  # UCI notation
    board_fen: str | None = None  # Optional FEN for context


class RobotResponse(BaseModel):
    """Response from robot execution."""

    success: bool
    error: str | None = None


@router.get("/status")
async def get_external_status():
    """Get the status of external services and operation mode."""
    manager = get_external_manager()
    status = await manager.get_status()
    return status


@router.put("/mode")
async def set_operation_mode(request: SetModeRequest):
    """Set the operation mode (simulation or ros).

    In simulation mode, mock clients are used.
    In ros mode, ROS topics are used for detection and robot control.
    """
    manager = get_external_manager()

    if request.mode not in ("simulation", "ros"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode: {request.mode}. Must be 'simulation' or 'ros'",
        )

    try:
        manager.set_operation_mode(request.mode)
        return {
            "status": "updated",
            "mode": request.mode,
            "using_ros_clients": manager.is_ros_mode_available(),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/detect/{game_id}", response_model=DetectionResponse)
async def request_detection(game_id: str):
    """Trigger board detection for a game.

    Captures the current board state from the camera detection system
    and updates the game session with the detected position.
    """
    orchestrator = get_orchestrator()

    session = orchestrator.get_session(game_id)
    if not session:
        raise HTTPException(status_code=404, detail="Game not found")

    try:
        result = await orchestrator.request_detection(game_id)
        return DetectionResponse(
            success=result.success,
            fen=result.fen,
            pieces=result.pieces,
            error=result.error,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/robot/{game_id}", response_model=RobotResponse)
async def send_robot_move(game_id: str, request: RobotMoveRequest):
    """Manually send a move to the robot.

    This is typically called automatically after agent deliberation,
    but can be used to manually execute moves on the physical board.
    """
    orchestrator = get_orchestrator()

    session = orchestrator.get_session(game_id)
    if not session:
        raise HTTPException(status_code=404, detail="Game not found")

    try:
        result = await orchestrator.send_to_robot(
            game_id, request.move, board_fen=request.board_fen
        )
        return RobotResponse(success=result.success, error=result.error)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/robot/{game_id}/home", response_model=RobotResponse)
async def home_robot(game_id: str):
    """Send the robot to its home position.

    This is useful for resetting the robot between games or
    after manual interventions.
    """
    orchestrator = get_orchestrator()

    session = orchestrator.get_session(game_id)
    if not session:
        raise HTTPException(status_code=404, detail="Game not found")

    manager = get_external_manager()

    try:
        result = await manager.robot_client.home()
        return RobotResponse(success=result.success, error=result.error)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def check_external_health():
    """Check the health of external services.

    Returns the health status of both the detection and robot systems.
    """
    manager = get_external_manager()

    detection_healthy = await manager.detection_client.health_check()
    robot_healthy = await manager.robot_client.health_check()

    return {
        "detection": {
            "healthy": detection_healthy,
        },
        "robot": {
            "healthy": robot_healthy,
        },
        "all_healthy": detection_healthy and robot_healthy,
    }


# Mock client configuration endpoints (for testing)


class MockDetectionConfig(BaseModel):
    """Configuration for mock detection client."""

    fen: str | None = None
    should_fail: bool = False
    error_message: str | None = None


class MockRobotConfig(BaseModel):
    """Configuration for mock robot client."""

    should_fail: bool = False
    error_message: str | None = None


@router.put("/mock/detection")
async def configure_mock_detection(config: MockDetectionConfig):
    """Configure the mock detection client (for testing).

    Only works when using mock clients.
    """
    manager = get_external_manager()

    if config.fen:
        try:
            manager.mock_detection.set_fen(config.fen)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid FEN: {e}")

    manager.mock_detection.set_should_fail(
        config.should_fail, config.error_message or "Detection failed"
    )

    return {
        "status": "configured",
        "fen": config.fen,
        "should_fail": config.should_fail,
    }


@router.put("/mock/robot")
async def configure_mock_robot(config: MockRobotConfig):
    """Configure the mock robot client (for testing).

    Only works when using mock clients.
    """
    manager = get_external_manager()

    manager.mock_robot.set_should_fail(
        config.should_fail, config.error_message or "Robot execution failed"
    )

    return {
        "status": "configured",
        "should_fail": config.should_fail,
    }


@router.get("/mock/robot/history")
async def get_mock_robot_history():
    """Get the move history from the mock robot (for testing).

    Returns all moves that have been sent to the mock robot client.
    """
    manager = get_external_manager()

    history = manager.mock_robot.get_move_history()
    return {
        "total_moves": len(history),
        "moves": [
            {
                "move": record.command.move,
                "from_square": record.command.from_square,
                "to_square": record.command.to_square,
                "piece_type": record.command.piece_type,
                "piece_color": record.command.piece_color,
                "is_capture": record.command.is_capture,
                "timestamp": record.timestamp.isoformat(),
                "success": record.success,
                "error": record.error,
            }
            for record in history
        ],
    }
