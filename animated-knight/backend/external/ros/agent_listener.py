"""ROS-based agent request listener.

Listens for agent move requests on /chess/agent_request and responds
with agent deliberation results on /chess/agent_opinions via the
orchestrator's generate_move_for_position() method.

This replaces direct HTTP calls from chess_manager to the animated-knight
backend, routing agent communication through ROS like perception and robot.
"""

import asyncio
import logging
from typing import Any

from backend.external.ros.bridge import ROSBridgeBase, ROSMessage

logger = logging.getLogger(__name__)


class ROSAgentListener:
    """Listens for agent requests via ROS and publishes deliberation results.

    Subscribes to a request topic and, on each incoming message, calls the
    orchestrator to generate a move.  The result is published back as an
    AgentOpinions message on the opinions topic.
    """

    def __init__(
        self,
        bridge: ROSBridgeBase,
        request_topic: str = "/chess/agent_request",
        opinions_topic: str = "/chess/agent_opinions",
        loop: asyncio.AbstractEventLoop | None = None,
    ) -> None:
        self._bridge = bridge
        self._request_topic = request_topic
        self._opinions_topic = opinions_topic
        self._loop = loop
        self._processing = False

        # Subscribe to incoming agent requests
        self._bridge.subscribe(request_topic, self._on_agent_request)
        logger.info(
            f"ROSAgentListener initialized: "
            f"request={request_topic}, opinions={opinions_topic}"
        )

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Set the asyncio event loop (call after the loop is running)."""
        self._loop = loop

    def _on_agent_request(self, message: ROSMessage) -> None:
        """Handle an incoming agent request (called from bridge reader thread)."""
        if self._loop is None:
            logger.error("ROSAgentListener: no event loop set, ignoring request")
            return

        if self._processing:
            logger.warning("ROSAgentListener: already processing a request, ignoring")
            return

        fen = message.data.get("fen", "")
        strategy = message.data.get("strategy", "hybrid")

        if not fen:
            logger.error("ROSAgentListener: received request with empty FEN")
            return

        logger.info(f"ROSAgentListener: received request — strategy={strategy}")
        logger.debug(f"ROSAgentListener: FEN={fen}")

        self._processing = True
        asyncio.run_coroutine_threadsafe(
            self._process_request(fen, strategy), self._loop
        )

    async def _process_request(self, fen: str, strategy: str) -> None:
        """Process an agent request asynchronously.

        Uses the streaming variant (stream_move_for_position) so that each
        deliberation event is broadcast to WebSocket clients in real time,
        keeping the animated-knight frontend's deliberation panel in sync.
        """
        try:
            from backend.orchestration import get_orchestrator
            from backend.api.websocket.manager import get_connection_manager

            orchestrator = get_orchestrator()
            ws_manager = get_connection_manager()

            # Determine agent color from FEN (side to move)
            agent_color = "white" if " w " in fen else "black"

            # Accumulators — rebuilt from streamed events
            choice_to_move: dict[str, str] = {}   # "A" → "e2e4"
            opinions: list[dict[str, Any]] = []
            selected_move_uci = ""
            voting_summary = ""

            async for event in orchestrator.stream_move_for_position(fen, strategy):
                # Broadcast every event to connected WebSocket clients
                ws_message = {
                    "type": event.event_type,
                    "agent_id": event.agent_id,
                    "data": event.data,
                }
                await ws_manager.broadcast_all(ws_message)

                # Collect data needed to build the ROS opinions response
                if event.event_type == "agent_proposal":
                    choice = event.data.get("choice", "")
                    move = event.data.get("move", "")
                    if choice and move:
                        choice_to_move[choice] = move

                elif event.event_type == "vote_cast":
                    voted_for = event.data.get("voted_for", "")
                    proposed_move = choice_to_move.get(voted_for, "")
                    opinions.append({
                        "piece_type": event.data.get("piece_type", ""),
                        "piece_color": agent_color,
                        "proposed_move": proposed_move,
                        "reasoning": event.data.get("reasoning", ""),
                        "confidence": 0.0,
                        "vote_weight": event.data.get("weight", 1),
                    })

                elif event.event_type == "deliberation_complete":
                    selected_move_uci = event.data.get("selected_move", "")
                    voting_summary = event.data.get("reasoning", "")

            opinions_data: dict[str, Any] = {
                "opinions": opinions,
                "selected_move_uci": selected_move_uci,
                "selected_move_san": "",
                "vote_confidence": 0.0,
                "voting_summary": voting_summary,
            }

            logger.info(
                f"ROSAgentListener: publishing result — "
                f"move={selected_move_uci}, "
                f"{len(opinions)} opinion(s)"
            )
            await self._bridge.publish(self._opinions_topic, opinions_data)

        except Exception as e:
            logger.error(f"ROSAgentListener: error processing request: {e}", exc_info=True)
            # Broadcast error so the frontend resets isAgentThinking
            try:
                from backend.api.websocket.manager import get_connection_manager
                await get_connection_manager().broadcast_all({
                    "type": "error",
                    "message": str(e),
                })
            except Exception:
                logger.debug("ROSAgentListener: could not broadcast error to WS clients")
            # Publish an empty-move response so chess_manager doesn't hang
            await self._bridge.publish(self._opinions_topic, {
                "opinions": [],
                "selected_move_uci": "",
                "selected_move_san": "",
                "vote_confidence": 0.0,
                "voting_summary": f"Error: {e}",
            })
        finally:
            self._processing = False
