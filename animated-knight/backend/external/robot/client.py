"""HTTP client for the real robot API.

This is a placeholder for when the real robot API is available.
Implement HttpRobotClient here following the RobotClient interface.

Example implementation:

```python
import httpx
from backend.external.interfaces import MoveCommand, RobotClient, RobotResult


class HttpRobotClient(RobotClient):
    def __init__(self, base_url: str, timeout: float = 30.0):
        self._base_url = base_url.rstrip('/')
        self._timeout = timeout
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
            return RobotResult(success=True)
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
            return RobotResult(success=True)
        except Exception as e:
            return RobotResult(success=False, error=str(e))
```
"""
