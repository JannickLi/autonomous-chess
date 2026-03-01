"""Chess Manager entry point.

Initializes all submodules and runs the main event loop with CLI interface.

Usage:
    python -m chess_manager.main [--config path/to/config.yaml] [--log-level DEBUG]

CLI commands (once running):
    start           - Start a new game (standard position)
    start <fen>     - Start from a FEN position
    move <uci>      - Submit human move (e.g., "move e2e4")
    capture         - Trigger perception capture (detect human move from board)
    status          - Show board and game state
    quit            - Exit
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
from typing import Any, Optional

from dotenv import load_dotenv

from chess_manager.config import ChessManagerConfig, get_config
from chess_manager.models import GameStateEvent
from chess_manager.ros_client import NewlineDelimitedBridgeClient, ROSClientManager
from chess_manager.state_manager import StateManager
from chess_manager.teacher import Teacher
from chess_manager.voice_in import VoiceIn
from chess_manager.voice_out import VoiceOut
from chess_manager.websocket_server import WebSocketServer

logger = logging.getLogger("chess_manager")


class ChessManager:
    """Top-level Chess Manager application."""

    def __init__(self, config: ChessManagerConfig) -> None:
        self._config = config
        self._shutdown_event = asyncio.Event()

        # Initialize submodules
        self._state_manager = StateManager(config)
        self._voice_out = VoiceOut(config.voice, self._state_manager._speak_request_queue)
        # Share VoiceOut's TTS instance with Teacher to avoid audio device conflicts
        self._teacher = Teacher(config.teacher, tts=self._voice_out._tts)
        self._voice_in = VoiceIn(config.voice, self._state_manager._human_move_queue)
        self._ws_server = WebSocketServer(config.websocket)

        # TCP bridge client for ROS2 (perception + robot)
        self._bridge: Optional[NewlineDelimitedBridgeClient] = None

        # Legacy ROS client manager (for LengthPrefixed connections)
        self._ros_clients: Optional[ROSClientManager] = None

        # Game loop task
        self._game_loop_task: Optional[asyncio.Task] = None

        # Wire callbacks
        self._state_manager._on_game_state_event = self._ws_server.broadcast_state_event
        self._ws_server._on_command = self._handle_ws_command

        # Wire voice status callbacks to broadcast via WebSocket
        def _broadcast_voice_status(data: dict) -> None:
            self._ws_server.broadcast_state_event(
                GameStateEvent(event_type="voice_status", data=data)
            )

        self._voice_out._on_voice_event = _broadcast_voice_status
        self._voice_in._on_voice_event = _broadcast_voice_status

        # Wire submodules to state manager
        self._state_manager._teacher = self._teacher
        self._state_manager._voice_in = self._voice_in
        self._state_manager._voice_out = self._voice_out

        logger.info("All submodules initialized.")

    async def start(self) -> None:
        """Start the Chess Manager and all submodules."""
        logger.info("Starting Chess Manager...")

        # Start WebSocket server
        await self._ws_server.start()

        # Connect to Chess Manager's own ros_bridge_server instance
        self._bridge = NewlineDelimitedBridgeClient(
            host="localhost",
            port=self._config.tcp.bridge_port,
            name="chess-manager-bridge",
        )
        bridge_port = self._config.tcp.bridge_port
        connected = self._bridge.connect(timeout=5.0)
        if connected:
            logger.info(f"Connected to chess_manager bridge on port {bridge_port}")
        else:
            logger.warning(
                f"Could not connect to chess_manager bridge on port {bridge_port} "
                f"(auto-reconnect enabled)"
            )

        # Wire bridge to state manager
        self._state_manager._bridge = self._bridge

        # Pre-subscribe to all response topics so ros_bridge_server creates
        # ROS2 subscriptions early (avoids race conditions with fast responses)
        if connected:
            for topic in (
                "/chess/perception_result",
                "/chess/move_result",
                "/chess/agent_opinions",
            ):
                self._bridge._ensure_subscribed(topic)
            logger.info("Pre-subscribed to response topics")

        # Start VoiceOut queue consumer
        self._voice_out.start()

        # Start game loop as background task
        self._game_loop_task = asyncio.create_task(
            self._state_manager.run_game_loop()
        )

        mode = "SIMULATION" if self._config.simulation_mode else "ROS"
        logger.info(f"Chess Manager started in {mode} mode.")
        logger.info("Type 'start' to begin a game, or 'help' for commands.")

    async def run(self) -> None:
        """Main run loop: start services then run CLI input loop."""
        await self.start()

        try:
            await self._cli_input_loop()
        except asyncio.CancelledError:
            pass
        finally:
            await self.shutdown()

    async def _cli_input_loop(self) -> None:
        """Read commands from stdin using asyncio."""
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await asyncio.get_event_loop().connect_read_pipe(
            lambda: protocol, sys.stdin
        )

        while not self._shutdown_event.is_set():
            try:
                sys.stdout.write("> ")
                sys.stdout.flush()

                # Race readline against shutdown event so Ctrl+C is responsive
                read_task = asyncio.ensure_future(reader.readline())
                shutdown_task = asyncio.ensure_future(self._shutdown_event.wait())
                done, pending = await asyncio.wait(
                    {read_task, shutdown_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for t in pending:
                    t.cancel()

                if shutdown_task in done:
                    break

                line = read_task.result()
                if not line:
                    break
                cmd = line.decode().strip()
                if not cmd:
                    continue
                await self._handle_command(cmd)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"CLI error: {e}")

    async def _handle_command(self, cmd: str) -> None:
        """Process a CLI command."""
        parts = cmd.split()
        command = parts[0].lower()

        if command == "start":
            fen = " ".join(parts[1:]) if len(parts) > 1 else None
            await self._state_manager.start_game(fen=fen)
            if fen:
                print(f"Game started from FEN: {self._state_manager.board_fen}")
            else:
                print("Game started. Human plays white.")

        elif command == "move" and len(parts) >= 2:
            uci = parts[1].lower()
            state = self._state_manager.state.value
            if state != "human_turn":
                print(f"Cannot submit move in state: {state}")
                return
            await self._state_manager._human_move_queue.put(uci)

        elif command == "capture":
            state = self._state_manager.state.value
            if state != "human_turn":
                print(f"Cannot capture in state: {state}")
                return
            await self._state_manager._human_move_queue.put("__capture__")
            print("Triggering perception capture...")

        elif command == "status":
            self._print_status()

        elif command in ("quit", "exit"):
            self.request_shutdown()

        elif command == "help":
            self._print_help()

        else:
            print(f"Unknown command: {cmd}. Type 'help' for commands.")

    async def _handle_ws_command(
        self, cmd_type: str, msg: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        """Handle a command received via WebSocket from the frontend."""
        sm = self._state_manager

        if cmd_type == "start":
            fen = msg.get("fen")
            await sm.start_game(fen=fen)
            return {"type": "status", "data": self._build_status()}

        elif cmd_type == "move":
            uci = msg.get("uci", "").strip().lower()
            if not uci:
                return {"type": "error", "message": "Missing 'uci' field"}
            state = sm.state.value
            if state != "human_turn":
                return {"type": "error", "message": f"Cannot submit move in state: {state}"}
            await sm._human_move_queue.put(uci)
            return None  # State update will come via broadcast

        elif cmd_type == "capture":
            state = sm.state.value
            if state != "human_turn":
                return {"type": "error", "message": f"Cannot capture in state: {state}"}
            await sm._human_move_queue.put("__capture__")
            return None  # State update will come via broadcast

        elif cmd_type == "status":
            return {"type": "status", "data": self._build_status()}

        else:
            return {"type": "error", "message": f"Unknown command: {cmd_type}"}

    def _build_status(self) -> dict[str, Any]:
        """Build a status dict for WebSocket responses."""
        sm = self._state_manager
        return {
            "state": sm.state.value,
            "fen": sm.board_fen,
            "turn": "white" if sm.board.turn else "black",
            "move_history": sm._move_history,
            "is_check": sm.board.is_check(),
            "is_game_over": sm.board.is_game_over(),
            "result": sm.board.result() if sm.board.is_game_over() else None,
            "legal_moves_count": sm.board.legal_moves.count(),
        }

    def _print_status(self) -> None:
        """Print current game status."""
        sm = self._state_manager
        print(f"\nState: {sm.state.value}")
        print(f"FEN: {sm.board_fen}")
        print(f"Turn: {'white' if sm.board.turn else 'black'}")
        print(f"Moves: {' '.join(sm._move_history) if sm._move_history else '(none)'}")
        if sm.board.is_check():
            print("CHECK!")
        if sm.board.is_game_over():
            print(f"Game over: {sm.board.result()}")
        # ASCII board
        print(f"\n{sm.board}\n")

    def _print_help(self) -> None:
        """Print available CLI commands."""
        print(
            "\nCommands:\n"
            "  start              - Start a new game from standard position\n"
            "  start <fen>        - Start from a FEN position\n"
            "                       e.g., 'start rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1'\n"
            "  move <uci>         - Submit human move (e.g., 'move e2e4')\n"
            "  capture            - Trigger perception capture\n"
            "  status             - Show board and game state\n"
            "  help               - Show this help\n"
            "  quit               - Exit\n"
        )

    async def shutdown(self) -> None:
        """Gracefully shut down all submodules."""
        logger.info("Shutting down Chess Manager...")

        # Signal state manager to stop first
        self._state_manager.request_shutdown()

        # Disconnect bridge BEFORE cancelling game loop — the game loop may
        # be blocked in wait_for_message(). Disconnecting the bridge closes
        # the socket and unblocks the reader thread, allowing the executor
        # future to complete.
        if self._bridge:
            self._bridge.disconnect()

        if self._ros_clients:
            self._ros_clients.disconnect_all()

        # Now cancel the game loop task (should unblock quickly)
        if self._game_loop_task and not self._game_loop_task.done():
            self._game_loop_task.cancel()
            try:
                await asyncio.wait_for(self._game_loop_task, timeout=3.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

        # Shutdown submodules
        await self._teacher.shutdown()
        self._voice_in.shutdown()
        self._voice_out.shutdown()
        await self._ws_server.stop()

        logger.info("Chess Manager shutdown complete.")

    def request_shutdown(self) -> None:
        """Signal the main loop to shut down."""
        self._shutdown_event.set()


def main() -> None:
    """Entry point."""
    load_dotenv()

    parser = argparse.ArgumentParser(description="Chess Manager - Central Orchestrator")
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to config YAML file",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log level (default: INFO)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Load config
    config = get_config(args.config)

    # Create manager
    manager = ChessManager(config)

    # Handle signals
    loop = asyncio.new_event_loop()

    def signal_handler():
        logger.info("Received shutdown signal")
        manager.request_shutdown()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)

    try:
        loop.run_until_complete(manager.run())
    finally:
        loop.close()


if __name__ == "__main__":
    main()
