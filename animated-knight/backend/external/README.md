# External API Integration

This module provides integration with external hardware systems for real-world chess playing:
- **Camera Detection System**: Captures the physical board state and returns the position as FEN
- **Robot Control System**: Executes chess moves on a physical board

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Chess Agents Backend                            │
│                                                                              │
│  ┌─────────────────┐    ┌──────────────────────┐    ┌───────────────────┐  │
│  │  ExternalServices│    │     Orchestrator     │    │   WebSocket       │  │
│  │     Manager      │◄───│                      │◄───│   Handlers        │  │
│  └────────┬─────────┘    └──────────────────────┘    └───────────────────┘  │
│           │                                                                  │
│           ▼                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                        Client Interfaces                             │    │
│  │  ┌─────────────────────┐         ┌─────────────────────┐            │    │
│  │  │   DetectionClient   │         │    RobotClient      │            │    │
│  │  │   (abstract)        │         │    (abstract)       │            │    │
│  │  └──────────┬──────────┘         └──────────┬──────────┘            │    │
│  │             │                               │                        │    │
│  │      ┌──────┴──────┐                 ┌──────┴──────┐                │    │
│  │      ▼             ▼                 ▼             ▼                │    │
│  │  ┌───────┐    ┌────────┐        ┌───────┐    ┌────────┐            │    │
│  │  │ Mock  │    │  HTTP  │        │ Mock  │    │  HTTP  │            │    │
│  │  │Client │    │ Client │        │Client │    │ Client │            │    │
│  │  └───────┘    └────┬───┘        └───────┘    └────┬───┘            │    │
│  └─────────────────────┼────────────────────────────┼──────────────────┘    │
│                        │                            │                        │
└────────────────────────┼────────────────────────────┼────────────────────────┘
                         │                            │
                         ▼                            ▼
              ┌──────────────────┐         ┌──────────────────┐
              │  Detection API   │         │    Robot API     │
              │  (Your Service)  │         │  (Your Service)  │
              └──────────────────┘         └──────────────────┘
```

## Operation Modes

| Mode | Description |
|------|-------------|
| `simulation` | Default. Uses mock clients. Board state managed in browser, no physical hardware. |
| `real` | Uses HTTP clients to call external APIs. Camera detects board, robot executes moves. |

---

## Interface Specifications

### DetectionClient

The detection client captures the current board state from a camera system.

```python
class DetectionClient(ABC):
    @abstractmethod
    async def capture(self) -> DetectionResult:
        """Request board state capture from detection system."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the detection system is available."""
        ...
```

#### DetectionResult

```python
@dataclass
class DetectionResult:
    success: bool                      # True if capture succeeded
    fen: str | None                    # Board position in FEN notation
    pieces: dict[str, str] | None      # Piece positions: {square: piece}
    error: str | None                  # Error message if failed
```

#### Expected API Response Format

Your detection API should return JSON in this format:

```json
{
  "success": true,
  "fen": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1",
  "pieces": {
    "a1": "R", "b1": "N", "c1": "B", "d1": "Q", "e1": "K", "f1": "B", "g1": "N", "h1": "R",
    "a2": "P", "b2": "P", "c2": "P", "d2": "P", "e4": "P", "f2": "P", "g2": "P", "h2": "P",
    "a7": "p", "b7": "p", "c7": "p", "d7": "p", "e7": "p", "f7": "p", "g7": "p", "h7": "p",
    "a8": "r", "b8": "n", "c8": "b", "d8": "q", "e8": "k", "f8": "b", "g8": "n", "h8": "r"
  },
  "error": null
}
```

**Piece notation:**
- Uppercase = White pieces: `K` (King), `Q` (Queen), `R` (Rook), `B` (Bishop), `N` (Knight), `P` (Pawn)
- Lowercase = Black pieces: `k`, `q`, `r`, `b`, `n`, `p`

**Square notation:** Standard algebraic (a1-h8), where a1 is bottom-left from White's perspective.

**Error response:**
```json
{
  "success": false,
  "fen": null,
  "pieces": null,
  "error": "Camera not connected"
}
```

---

### RobotClient

The robot client sends move commands to a robotic arm that executes moves on the physical board.

```python
class RobotClient(ABC):
    @abstractmethod
    async def execute_move(self, command: MoveCommand) -> RobotResult:
        """Send move command to robot system."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the robot system is available."""
        ...

    @abstractmethod
    async def home(self) -> RobotResult:
        """Send robot to home position."""
        ...
```

#### MoveCommand

The move command contains all information needed to execute a chess move:

```python
@dataclass
class MoveCommand:
    move: str                    # UCI notation: "e2e4", "e7e8q" (promotion)
    from_square: str             # Source square: "e2"
    to_square: str               # Destination square: "e4"
    piece_type: str              # "pawn", "knight", "bishop", "rook", "queen", "king"
    piece_color: str             # "white" or "black"
    is_capture: bool             # True if capturing an opponent's piece
    captured_piece: str | None   # Type of captured piece: "pawn", "knight", etc.
    is_castling: bool            # True for castling moves (O-O or O-O-O)
    is_en_passant: bool          # True for en passant captures
    is_promotion: bool           # True for pawn promotion
    promotion_piece: str | None  # "queen", "rook", "bishop", or "knight"
    board_fen: str               # Current board state for context
```

#### Expected API Request Format

Your robot API will receive POST requests with this JSON body:

```json
{
  "move": "e2e4",
  "from_square": "e2",
  "to_square": "e4",
  "piece_type": "pawn",
  "piece_color": "white",
  "is_capture": false,
  "captured_piece": null,
  "is_castling": false,
  "is_en_passant": false,
  "is_promotion": false,
  "promotion_piece": null,
  "board_fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
}
```

**Capture example:**
```json
{
  "move": "d4e5",
  "from_square": "d4",
  "to_square": "e5",
  "piece_type": "pawn",
  "piece_color": "white",
  "is_capture": true,
  "captured_piece": "pawn",
  "is_castling": false,
  "is_en_passant": false,
  "is_promotion": false,
  "promotion_piece": null,
  "board_fen": "rnbqkbnr/pppp1ppp/8/4p3/3P4/8/PPP1PPPP/RNBQKBNR w KQkq e6 0 2"
}
```

**Castling example (kingside):**
```json
{
  "move": "e1g1",
  "from_square": "e1",
  "to_square": "g1",
  "piece_type": "king",
  "piece_color": "white",
  "is_capture": false,
  "captured_piece": null,
  "is_castling": true,
  "is_en_passant": false,
  "is_promotion": false,
  "promotion_piece": null,
  "board_fen": "r3k2r/pppppppp/8/8/8/8/PPPPPPPP/R3K2R w KQkq - 0 1"
}
```
*Note: For castling, the robot should move both the king (e1→g1) and the rook (h1→f1).*

**Promotion example:**
```json
{
  "move": "e7e8q",
  "from_square": "e7",
  "to_square": "e8",
  "piece_type": "pawn",
  "piece_color": "white",
  "is_capture": false,
  "captured_piece": null,
  "is_castling": false,
  "is_en_passant": false,
  "is_promotion": true,
  "promotion_piece": "queen",
  "board_fen": "8/4P3/8/8/8/8/8/4K2k w - - 0 1"
}
```
*Note: For promotion, the robot should remove the pawn and place a queen (or other piece) on the destination square.*

**En passant example:**
```json
{
  "move": "d5e6",
  "from_square": "d5",
  "to_square": "e6",
  "piece_type": "pawn",
  "piece_color": "white",
  "is_capture": true,
  "captured_piece": "pawn",
  "is_castling": false,
  "is_en_passant": true,
  "is_promotion": false,
  "promotion_piece": null,
  "board_fen": "rnbqkbnr/pppp1ppp/8/3Pp3/8/8/PPP1PPPP/RNBQKBNR w KQkq e6 0 3"
}
```
*Note: For en passant, the captured pawn is on a different square (e5) than the destination (e6). The robot should remove the pawn from e5.*

#### RobotResult

```python
@dataclass
class RobotResult:
    success: bool           # True if move executed successfully
    error: str | None       # Error message if failed
```

#### Expected API Response Format

**Success:**
```json
{
  "success": true,
  "error": null
}
```

**Failure:**
```json
{
  "success": false,
  "error": "Gripper failed to close"
}
```

---

## API Endpoints Your Services Should Implement

### Detection Service

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/capture` | POST | Capture current board state, return FEN and pieces |
| `/health` | GET | Return 200 if system is operational |

### Robot Service

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/move` | POST | Execute a move (body: MoveCommand JSON) |
| `/home` | POST | Return robot to home/rest position |
| `/health` | GET | Return 200 if system is operational |

---

## Configuration

Set these environment variables to enable real mode:

```bash
# Enable real mode by default (optional, can also toggle in UI)
OPERATION_MODE=real

# Your detection API base URL
DETECTION_API_URL=http://192.168.1.100:5000

# Your robot API base URL
ROBOT_API_URL=http://192.168.1.101:5001
```

Or in `.env` file:
```
OPERATION_MODE=simulation
DETECTION_API_URL=http://localhost:5000
ROBOT_API_URL=http://localhost:5001
```

---

## Implementing Real Clients

Once your external APIs are ready, implement the HTTP clients:

### 1. Detection HTTP Client

Create `backend/external/detection/http_client.py`:

```python
import httpx
from backend.external.interfaces import DetectionClient, DetectionResult


class HttpDetectionClient(DetectionClient):
    def __init__(self, base_url: str, timeout: float = 10.0):
        self._base_url = base_url.rstrip('/')
        self._client = httpx.AsyncClient(timeout=timeout)

    async def capture(self) -> DetectionResult:
        try:
            response = await self._client.post(f"{self._base_url}/capture")
            response.raise_for_status()
            data = response.json()
            return DetectionResult(
                success=data.get("success", False),
                fen=data.get("fen"),
                pieces=data.get("pieces"),
                error=data.get("error"),
            )
        except httpx.HTTPStatusError as e:
            return DetectionResult(
                success=False,
                error=f"HTTP {e.response.status_code}: {e.response.text}",
            )
        except Exception as e:
            return DetectionResult(success=False, error=str(e))

    async def health_check(self) -> bool:
        try:
            response = await self._client.get(f"{self._base_url}/health")
            return response.status_code == 200
        except Exception:
            return False
```

### 2. Robot HTTP Client

Create `backend/external/robot/http_client.py`:

```python
import httpx
from backend.external.interfaces import MoveCommand, RobotClient, RobotResult


class HttpRobotClient(RobotClient):
    def __init__(self, base_url: str, timeout: float = 30.0):
        self._base_url = base_url.rstrip('/')
        self._client = httpx.AsyncClient(timeout=timeout)

    async def execute_move(self, command: MoveCommand) -> RobotResult:
        try:
            response = await self._client.post(
                f"{self._base_url}/move",
                json={
                    "move": command.move,
                    "from_square": command.from_square,
                    "to_square": command.to_square,
                    "piece_type": command.piece_type,
                    "piece_color": command.piece_color,
                    "is_capture": command.is_capture,
                    "captured_piece": command.captured_piece,
                    "is_castling": command.is_castling,
                    "is_en_passant": command.is_en_passant,
                    "is_promotion": command.is_promotion,
                    "promotion_piece": command.promotion_piece,
                    "board_fen": command.board_fen,
                },
            )
            response.raise_for_status()
            data = response.json()
            return RobotResult(
                success=data.get("success", False),
                error=data.get("error"),
            )
        except httpx.HTTPStatusError as e:
            return RobotResult(
                success=False,
                error=f"HTTP {e.response.status_code}: {e.response.text}",
            )
        except Exception as e:
            return RobotResult(success=False, error=str(e))

    async def health_check(self) -> bool:
        try:
            response = await self._client.get(f"{self._base_url}/health")
            return response.status_code == 200
        except Exception:
            return False

    async def home(self) -> RobotResult:
        try:
            response = await self._client.post(f"{self._base_url}/home")
            response.raise_for_status()
            data = response.json()
            return RobotResult(
                success=data.get("success", False),
                error=data.get("error"),
            )
        except Exception as e:
            return RobotResult(success=False, error=str(e))
```

### 3. Update Manager to Use Real Clients

Modify `backend/external/manager.py` to use HTTP clients when URLs are configured:

```python
def __init__(self, ...):
    # ... existing code ...

    # Initialize real clients if URLs are provided
    if detection_api_url:
        from backend.external.detection.http_client import HttpDetectionClient
        self._real_detection = HttpDetectionClient(detection_api_url)

    if robot_api_url:
        from backend.external.robot.http_client import HttpRobotClient
        self._real_robot = HttpRobotClient(robot_api_url)
```

---

## Real Mode Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    User clicks "Capture Board"                   │
└─────────────────────────────────┬───────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│ 1. DETECTION                                                     │
│    WebSocket: detection_started                                  │
│    POST → Detection API /capture                                 │
│    Response: { fen, pieces }                                     │
│    WebSocket: detection_complete { fen, pieces }                 │
│    Board UI updates to show detected position                    │
└─────────────────────────────────┬───────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. AGENT DELIBERATION                                           │
│    WebSocket: deliberation_started                               │
│    Supervisor proposes candidate moves                           │
│    WebSocket: agent_proposal (×3)                                │
│    Piece agents vote                                             │
│    WebSocket: vote_cast (×N)                                     │
│    WebSocket: deliberation_complete { selected_move }            │
└─────────────────────────────────┬───────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. ROBOT EXECUTION                                               │
│    WebSocket: robot_executing { move, san }                      │
│    POST → Robot API /move { MoveCommand }                        │
│    Robot physically moves the piece                              │
│    WebSocket: robot_complete { success }                         │
│    Move shown on board UI                                        │
└─────────────────────────────────────────────────────────────────┘
```

---

## Testing with Mock Clients

The mock clients can be configured via API for testing:

```bash
# Set mock detection to return a specific position
curl -X PUT http://localhost:8000/api/external/mock/detection \
  -H "Content-Type: application/json" \
  -d '{"fen": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"}'

# Make mock detection fail
curl -X PUT http://localhost:8000/api/external/mock/detection \
  -H "Content-Type: application/json" \
  -d '{"should_fail": true, "error_message": "Camera disconnected"}'

# Make mock robot fail
curl -X PUT http://localhost:8000/api/external/mock/robot \
  -H "Content-Type: application/json" \
  -d '{"should_fail": true, "error_message": "Gripper malfunction"}'

# Get mock robot move history
curl http://localhost:8000/api/external/mock/robot/history
```

---

## Chess Agents API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/external/status` | GET | Get current mode and service status |
| `/api/external/mode` | PUT | Set operation mode (`simulation` or `real`) |
| `/api/external/detect/{game_id}` | POST | Trigger board detection |
| `/api/external/robot/{game_id}` | POST | Send move to robot |
| `/api/external/robot/{game_id}/home` | POST | Send robot to home position |
| `/api/external/health` | GET | Check health of external services |

---

## WebSocket Events

| Event | Direction | Description |
|-------|-----------|-------------|
| `request_real_turn` | Client → Server | Start real mode turn (detect → agent → robot) |
| `detection_started` | Server → Client | Detection capture initiated |
| `detection_complete` | Server → Client | Detection finished, includes `{ fen, pieces }` |
| `robot_executing` | Server → Client | Robot started executing move |
| `robot_complete` | Server → Client | Robot finished, includes `{ success, error }` |

---

## Questions?

If you have questions about the interface or need clarification on any format, check the mock client implementations:
- `backend/external/detection/mock_client.py`
- `backend/external/robot/mock_client.py`

These show exactly what data structures are used and expected.
