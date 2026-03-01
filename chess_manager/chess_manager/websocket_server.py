"""WebSocket server for frontend communication.

Provides real-time game state updates and accepts commands from the
Chess Manager frontend. Broadcasts game_state and agent_deliberation
events to all connected clients.

Protocol (JSON messages):
  Server -> Client:
    {"type": "game_state", "data": {...}, "timestamp": float}
    {"type": "agent_deliberation", "data": {...}, "timestamp": float}
    {"type": "status", "data": {...}}
    {"type": "error", "message": str}
    {"type": "connected", "client_id": str}

  Client -> Server:
    {"type": "start"}
    {"type": "move", "uci": str}
    {"type": "capture"}
    {"type": "status"}
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any, Callable, Coroutine, Optional

import websockets
from websockets.asyncio.server import Server, ServerConnection

from chess_manager.config import WebSocketConfig
from chess_manager.models import GameStateEvent

logger = logging.getLogger(__name__)


class WebSocketServer:
    """WebSocket server for frontend communication."""

    def __init__(self, config: WebSocketConfig) -> None:
        self._config = config
        self._server: Optional[Server] = None
        self._clients: dict[str, ServerConnection] = {}
        self._running = False

        # Command handler callback — set by main.py
        self._on_command: Optional[
            Callable[[str, dict[str, Any]], Coroutine[Any, Any, Optional[dict[str, Any]]]]
        ] = None

        logger.info(
            f"WebSocketServer initialized "
            f"(will listen on {config.host}:{config.port})"
        )

    async def start(self) -> None:
        """Start the WebSocket server."""
        self._server = await websockets.serve(
            self._handle_client,
            self._config.host,
            self._config.port,
        )
        self._running = True
        logger.info(f"WebSocket server listening on ws://{self._config.host}:{self._config.port}")

    async def stop(self) -> None:
        """Stop the WebSocket server."""
        self._running = False
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        self._clients.clear()
        logger.info("WebSocketServer stopped")

    async def _handle_client(self, websocket: ServerConnection) -> None:
        """Handle a single WebSocket client connection."""
        client_id = str(uuid.uuid4())[:8]
        self._clients[client_id] = websocket
        logger.info(f"Client {client_id} connected ({len(self._clients)} total)")

        # Send welcome message
        await self._send(websocket, {
            "type": "connected",
            "client_id": client_id,
        })

        try:
            async for raw in websocket:
                try:
                    msg = json.loads(raw)
                    await self._handle_message(client_id, websocket, msg)
                except json.JSONDecodeError:
                    await self._send(websocket, {
                        "type": "error",
                        "message": "Invalid JSON",
                    })
        except websockets.ConnectionClosed:
            pass
        finally:
            self._clients.pop(client_id, None)
            logger.info(f"Client {client_id} disconnected ({len(self._clients)} total)")

    async def _handle_message(
        self, client_id: str, websocket: ServerConnection, msg: dict[str, Any]
    ) -> None:
        """Route an incoming client message."""
        msg_type = msg.get("type", "")

        if msg_type == "ping":
            await self._send(websocket, {"type": "pong"})
            return

        if not self._on_command:
            await self._send(websocket, {
                "type": "error",
                "message": "No command handler registered",
            })
            return

        try:
            result = await self._on_command(msg_type, msg)
            if result:
                await self._send(websocket, result)
        except Exception as e:
            logger.error(f"Error handling command '{msg_type}' from {client_id}: {e}")
            await self._send(websocket, {
                "type": "error",
                "message": str(e),
            })

    def broadcast_state_event(self, event: GameStateEvent) -> None:
        """Broadcast a game state event to all connected clients."""
        if not self._clients:
            return

        message = {
            "type": event.event_type,
            "data": event.data,
            "timestamp": event.timestamp,
        }

        asyncio.ensure_future(self._broadcast(message))

    def broadcast_agent_event(self, event: GameStateEvent) -> None:
        """Broadcast an agent event to all connected clients."""
        self.broadcast_state_event(event)

    async def _broadcast(self, message: dict[str, Any]) -> None:
        """Send a message to all connected clients."""
        if not self._clients:
            return

        payload = json.dumps(message)
        dead: list[str] = []

        # Snapshot to avoid RuntimeError if clients connect/disconnect mid-broadcast
        snapshot = list(self._clients.items())

        for client_id, ws in snapshot:
            try:
                await ws.send(payload)
            except websockets.ConnectionClosed:
                dead.append(client_id)
            except Exception as e:
                logger.error(f"Error sending to {client_id}: {e}")
                dead.append(client_id)

        for cid in dead:
            self._clients.pop(cid, None)

    @staticmethod
    async def _send(websocket: ServerConnection, message: dict[str, Any]) -> None:
        """Send a JSON message to a single client."""
        try:
            await websocket.send(json.dumps(message))
        except websockets.ConnectionClosed:
            pass
