"""WebSocket connection management."""

import json
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket

from backend.core import get_logger

logger = get_logger(__name__)


@dataclass
class Connection:
    """Represents a WebSocket connection."""

    websocket: WebSocket
    game_id: str | None = None
    client_id: str | None = None


class ConnectionManager:
    """Manages WebSocket connections for real-time updates."""

    def __init__(self):
        self._connections: dict[str, Connection] = {}
        self._game_connections: dict[str, set[str]] = {}  # game_id -> set of conn_ids

    async def connect(
        self, websocket: WebSocket, client_id: str, game_id: str | None = None
    ) -> Connection:
        """Accept a new WebSocket connection."""
        await websocket.accept()

        conn = Connection(
            websocket=websocket,
            game_id=game_id,
            client_id=client_id,
        )
        self._connections[client_id] = conn

        if game_id:
            if game_id not in self._game_connections:
                self._game_connections[game_id] = set()
            self._game_connections[game_id].add(client_id)

        logger.info(f"WebSocket connected: {client_id}, game: {game_id}")
        return conn

    def disconnect(self, client_id: str) -> None:
        """Remove a connection."""
        conn = self._connections.pop(client_id, None)
        if conn and conn.game_id:
            game_conns = self._game_connections.get(conn.game_id, set())
            game_conns.discard(client_id)
            if not game_conns:
                self._game_connections.pop(conn.game_id, None)

        logger.info(f"WebSocket disconnected: {client_id}")

    async def send_to_client(self, client_id: str, message: dict[str, Any]) -> bool:
        """Send a message to a specific client."""
        conn = self._connections.get(client_id)
        if not conn:
            return False

        try:
            await conn.websocket.send_json(message)
            return True
        except Exception as e:
            logger.error(f"Failed to send to {client_id}: {e}")
            self.disconnect(client_id)
            return False

    async def broadcast_to_game(
        self, game_id: str, message: dict[str, Any], exclude: str | None = None
    ) -> int:
        """Broadcast a message to all clients watching a game."""
        client_ids = self._game_connections.get(game_id, set())
        sent = 0

        for client_id in list(client_ids):
            if client_id == exclude:
                continue
            if await self.send_to_client(client_id, message):
                sent += 1

        return sent

    async def broadcast_all(
        self, message: dict[str, Any], exclude: str | None = None
    ) -> int:
        """Broadcast a message to all connected clients."""
        sent = 0
        for client_id in list(self._connections.keys()):
            if client_id == exclude:
                continue
            if await self.send_to_client(client_id, message):
                sent += 1
        return sent

    def subscribe_to_game(self, client_id: str, game_id: str) -> bool:
        """Subscribe a client to a game's updates."""
        conn = self._connections.get(client_id)
        if not conn:
            return False

        # Remove from old game if any
        if conn.game_id and conn.game_id != game_id:
            old_conns = self._game_connections.get(conn.game_id, set())
            old_conns.discard(client_id)

        # Add to new game
        conn.game_id = game_id
        if game_id not in self._game_connections:
            self._game_connections[game_id] = set()
        self._game_connections[game_id].add(client_id)

        return True

    def unsubscribe_from_game(self, client_id: str) -> bool:
        """Unsubscribe a client from their current game."""
        conn = self._connections.get(client_id)
        if not conn or not conn.game_id:
            return False

        game_conns = self._game_connections.get(conn.game_id, set())
        game_conns.discard(client_id)
        conn.game_id = None

        return True

    def get_connection_count(self) -> int:
        """Get total number of connections."""
        return len(self._connections)

    def get_game_connection_count(self, game_id: str) -> int:
        """Get number of connections watching a game."""
        return len(self._game_connections.get(game_id, set()))


# Global connection manager instance
_manager: ConnectionManager | None = None


def get_connection_manager() -> ConnectionManager:
    """Get the global connection manager instance."""
    global _manager
    if _manager is None:
        _manager = ConnectionManager()
    return _manager
