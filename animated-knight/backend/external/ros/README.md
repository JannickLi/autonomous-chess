# ROS Integration Module

This module provides ROS-based communication for the chess-agents system to interface with the detection module and robot engine.

## Architecture

```
backend/external/ros/
├── __init__.py           # Module exports
├── bridge.py             # ROS bridge abstraction (Mock, ROS1, ROS2)
├── detection_client.py   # Detection client using ROS topics
├── robot_client.py       # Robot client using ROS topics
└── README.md             # This file
```

## Operation Modes

### Simulation Mode (Default)

When ROS is not installed (e.g., on macOS), the system automatically uses `MockROSBridge`:

```bash
export OPERATION_MODE=simulation  # or just don't set it
python -m uvicorn backend.main:app --reload
```

The mock bridge:
- Records all published messages for inspection
- Allows simulating incoming messages via `simulate_message()`
- Can configure automatic responses for testing

### ROS Mode

When ROS is available and `OPERATION_MODE=ros`:

```bash
export OPERATION_MODE=ros
export ROS_MASTER_URI=http://localhost:11311
python -m uvicorn backend.main:app --reload
```

## Topic Configuration

All topics can be configured via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `ROS_CAPTURE_TOPIC` | `/capture` | Trigger board detection |
| `ROS_POSITION_TOPIC` | `/position` | Receive board state |
| `ROS_MOVE_TOPIC` | `/move` | Send move commands |
| `ROS_MOVE_RESULT_TOPIC` | `/move_result` | Receive move results |
| `ROS_ROBOT_HOME_TOPIC` | `/robot_home` | Send robot to home |
| `ROS_ROBOT_STATUS_TOPIC` | `/robot_status` | Robot health status |
| `ROS_DETECTION_STATUS_TOPIC` | `/detection_status` | Detection health |
| `ROS_CAM_TOPIC` | `/cam` | Camera image stream |
| `ROS_DETECTION_TIMEOUT` | `10.0` | Timeout for capture (seconds) |
| `ROS_MOVE_TIMEOUT` | `60.0` | Timeout for moves (seconds) |

## Usage

### Programmatic Access

```python
from backend.external.manager import get_external_manager

manager = get_external_manager()

# Check current mode
print(manager.operation_mode)  # "simulation", "real", or "ros"

# Get clients
detection = manager.detection_client
robot = manager.robot_client

# Capture board state
result = await detection.capture()
if result.success:
    print(f"FEN: {result.fen}")

# Execute a move
from backend.external.interfaces import MoveCommand
command = MoveCommand(
    move="e2e4",
    from_square="e2",
    to_square="e4",
    piece_type="pawn",
    piece_color="white",
    is_capture=False,
    captured_piece=None,
    is_castling=False,
    is_en_passant=False,
    is_promotion=False,
    promotion_piece=None,
    board_fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
)
result = await robot.execute_move(command)
```

### Testing with Mock Bridge

```python
from backend.external.ros.bridge import MockROSBridge

bridge = MockROSBridge()

# Configure auto-response for capture
bridge.set_simulated_response(
    trigger_topic="/capture",
    response_topic="/position",
    response_data={
        "success": True,
        "fen": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1",
        "squares": ["a1", "b1", ...],
        "pieces": ["R", "N", ...],
        "confidence": 0.98,
    }
)

# Use with clients
from backend.external.ros.detection_client import ROSDetectionClient
detection = ROSDetectionClient(bridge)
result = await detection.capture()  # Gets the simulated response

# Inspect published messages
messages = bridge.get_published_messages("/capture")
```

## Implementation Status

| Component | Status | Notes |
|-----------|--------|-------|
| MockROSBridge | Complete | For simulation/testing |
| ROS1Bridge | Stub | Requires chess_msgs package |
| ROS2Bridge | Stub | Requires chess_msgs package |
| ROSDetectionClient | Complete | Works with any bridge |
| ROSRobotClient | Complete | Works with any bridge |

## Next Steps

To complete ROS integration after repository merge:

1. Create `chess_msgs` package with message definitions
2. Implement `ROS1Bridge.publish()` and `wait_for_message()`
3. Add message type converters
4. Test with actual ROS nodes

See `/docs/ROS_ARCHITECTURE.md` for full architecture documentation.
