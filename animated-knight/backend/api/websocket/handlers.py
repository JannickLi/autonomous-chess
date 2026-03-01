"""WebSocket event handlers."""

import json
from uuid import uuid4

from fastapi import WebSocket, WebSocketDisconnect

from backend.core import get_logger
from backend.orchestration import get_orchestrator

from .manager import get_connection_manager

logger = get_logger(__name__)


async def websocket_endpoint(websocket: WebSocket, game_id: str | None = None):
    """
    Main WebSocket endpoint for real-time game updates.

    Clients can:
    - Subscribe to game updates
    - Request agent moves with streaming deliberation
    - Receive move notifications
    """
    manager = get_connection_manager()
    client_id = str(uuid4())

    conn = await manager.connect(websocket, client_id, game_id)

    try:
        # Send welcome message
        await websocket.send_json({
            "type": "connected",
            "client_id": client_id,
            "game_id": game_id,
        })

        # Main message loop
        while True:
            data = await websocket.receive_json()
            await handle_message(client_id, data)

    except WebSocketDisconnect:
        manager.disconnect(client_id)
    except Exception as e:
        logger.error(f"WebSocket error for {client_id}: {e}")
        manager.disconnect(client_id)


async def handle_message(client_id: str, data: dict):
    """Handle an incoming WebSocket message."""
    logger.info(f"WebSocket message from {client_id}: {data}")
    manager = get_connection_manager()
    orchestrator = get_orchestrator()

    message_type = data.get("type")

    if message_type == "subscribe":
        # Subscribe to a game
        game_id = data.get("game_id")
        if game_id:
            manager.subscribe_to_game(client_id, game_id)
            await manager.send_to_client(client_id, {
                "type": "subscribed",
                "game_id": game_id,
            })

    elif message_type == "unsubscribe":
        # Unsubscribe from current game
        manager.unsubscribe_from_game(client_id)
        await manager.send_to_client(client_id, {
            "type": "unsubscribed",
        })

    elif message_type == "request_agent_move":
        # Request an agent move with streaming
        game_id = data.get("game_id")
        if not game_id:
            await manager.send_to_client(client_id, {
                "type": "error",
                "message": "game_id required",
            })
            return

        try:
            async for event in orchestrator.stream_agent_move(game_id):
                # Send event to requesting client
                await manager.send_to_client(client_id, {
                    "type": event.event_type,
                    "agent_id": event.agent_id,
                    "data": event.data,
                })

                # Also broadcast to other watchers for certain events
                if event.event_type in ["agent_proposal", "vote_cast", "agent_move", "deliberation_complete"]:
                    await manager.broadcast_to_game(game_id, {
                        "type": event.event_type,
                        "agent_id": event.agent_id,
                        "data": event.data,
                    }, exclude=client_id)

        except ValueError as e:
            await manager.send_to_client(client_id, {
                "type": "error",
                "message": str(e),
            })

    elif message_type == "make_move":
        # Make a player move
        game_id = data.get("game_id")
        move = data.get("move")

        if not game_id or not move:
            await manager.send_to_client(client_id, {
                "type": "error",
                "message": "game_id and move required",
            })
            return

        try:
            session, move_info = await orchestrator.make_player_move(game_id, move)

            # Send confirmation to client
            await manager.send_to_client(client_id, {
                "type": "move_made",
                **move_info,
            })

            # Broadcast to other watchers
            await manager.broadcast_to_game(game_id, {
                "type": "opponent_move",
                **move_info,
            }, exclude=client_id)

        except ValueError as e:
            await manager.send_to_client(client_id, {
                "type": "error",
                "message": str(e),
            })

    elif message_type == "get_state":
        # Get current game state
        game_id = data.get("game_id")
        if not game_id:
            await manager.send_to_client(client_id, {
                "type": "error",
                "message": "game_id required",
            })
            return

        session = orchestrator.get_session(game_id)
        if not session:
            await manager.send_to_client(client_id, {
                "type": "error",
                "message": "Game not found",
            })
            return

        await manager.send_to_client(client_id, {
            "type": "game_state",
            **session.to_dict(),
        })

    elif message_type == "request_real_turn":
        # Request a full real-mode turn: detect → agent → robot
        game_id = data.get("game_id")
        if not game_id:
            await manager.send_to_client(client_id, {
                "type": "error",
                "message": "game_id required",
            })
            return

        try:
            async for event in orchestrator.real_mode_turn(game_id):
                # Send event to requesting client
                await manager.send_to_client(client_id, {
                    "type": event.event_type,
                    "agent_id": event.agent_id,
                    "data": event.data,
                })

                # Broadcast certain events to other watchers
                broadcast_events = [
                    "detection_started",
                    "detection_complete",
                    "agent_proposal",
                    "vote_cast",
                    "agent_move",
                    "deliberation_complete",
                    "robot_executing",
                    "robot_complete",
                ]
                if event.event_type in broadcast_events:
                    await manager.broadcast_to_game(game_id, {
                        "type": event.event_type,
                        "agent_id": event.agent_id,
                        "data": event.data,
                    }, exclude=client_id)

        except ValueError as e:
            await manager.send_to_client(client_id, {
                "type": "error",
                "message": str(e),
            })

    elif message_type == "ping":
        # Heartbeat
        await manager.send_to_client(client_id, {"type": "pong"})

    else:
        await manager.send_to_client(client_id, {
            "type": "error",
            "message": f"Unknown message type: {message_type}",
        })
