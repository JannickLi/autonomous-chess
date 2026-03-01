"""State Manager - Core game orchestration with state machine.

The State Manager is the heart of the Chess Manager. It:
- Tracks authoritative game state (board position, move history)
- Manages the game state machine (WAITING -> HUMAN_TURN -> ... -> GAME_OVER)
- Runs the main game loop as an asyncio task
- Integrates perception (board diffing), agent deliberation, and robot execution
"""

from __future__ import annotations

import asyncio
import logging
from typing import Callable, Optional

import chess

from chess_manager.config import ChessManagerConfig
from chess_manager.models import (
    AgentDecision,
    AgentOpinion,
    GameState,
    GameStateEvent,
    MoveResult,
    PlayerColor,
    SpeakRequest,
)

logger = logging.getLogger(__name__)

# Max retries for perception capture when FEN is invalid
_MAX_CAPTURE_RETRIES = 3

# Max retries when agent returns illegal/invalid moves
_MAX_AGENT_RETRIES = 3

# Piece type map for building MoveCommands (reused from orchestrator.send_to_robot)
_PIECE_TYPE_MAP = {
    chess.PAWN: "pawn",
    chess.KNIGHT: "knight",
    chess.BISHOP: "bishop",
    chess.ROOK: "rook",
    chess.QUEEN: "queen",
    chess.KING: "king",
}


class StateManager:
    """Central game state machine and orchestrator."""

    def __init__(self, config: ChessManagerConfig) -> None:
        self._config = config
        self._state = GameState.WAITING
        self._board = chess.Board()
        self._human_color = PlayerColor(config.game.human_color)
        self._move_history: list[str] = []  # UCI moves

        # Queue for receiving human moves (from CLI or perception)
        self._human_move_queue: asyncio.Queue[str] = asyncio.Queue()

        # Shutdown signal
        self._shutdown = asyncio.Event()

        # Async queues for submodule communication (voice stubs)
        self._voice_command_queue: asyncio.Queue = asyncio.Queue()
        self._speak_request_queue: asyncio.Queue = asyncio.Queue()

        # External clients (set by main.py during wiring)
        self._bridge = None  # NewlineDelimitedBridgeClient instance

        # Submodules (set by main.py during wiring)
        self._teacher = None  # Teacher instance
        self._voice_in = None  # VoiceIn instance
        self._voice_out = None  # VoiceOut instance

        # Callbacks (set by main.py during wiring)
        self._on_game_state_event: Optional[Callable] = None

        # Track in-flight teacher task so we can cancel stale analysis
        self._teacher_task: Optional[asyncio.Task] = None

        logger.info(f"StateManager initialized. Human plays {self._human_color.value}.")

    @property
    def state(self) -> GameState:
        """Current state machine state."""
        return self._state

    @property
    def board(self) -> chess.Board:
        """Current board position."""
        return self._board

    @property
    def board_fen(self) -> str:
        """Current board FEN."""
        return self._board.fen()

    def request_shutdown(self) -> None:
        """Signal the game loop to stop."""
        self._shutdown.set()

    # ── State Transitions ─────────────────────────────────────────────

    def _transition(self, new_state: GameState) -> None:
        """Transition to a new state and emit event."""
        old_state = self._state
        self._state = new_state
        logger.info(f"State transition: {old_state.value} -> {new_state.value}")
        self._emit_event(
            GameStateEvent(
                event_type="game_state",
                data={
                    "state": new_state.value,
                    "previous_state": old_state.value,
                    "fen": self._board.fen(),
                    "turn": "white" if self._board.turn == chess.WHITE else "black",
                    "move_history": self._move_history,
                    "is_check": self._board.is_check(),
                    "is_game_over": self._board.is_game_over(),
                },
            )
        )

    def _emit_event(self, event: GameStateEvent) -> None:
        """Push event to WebSocket (when wired)."""
        if self._on_game_state_event:
            try:
                self._on_game_state_event(event)
            except Exception as e:
                logger.error(f"Error emitting event: {e}")

    def _launch_teacher(self, fen: str, move_uci: str) -> None:
        """Cancel any in-flight teacher task and start a new analysis.

        This prevents a stale analysis (e.g. from a previous illegal move
        attempt) from speaking over a newer move.
        """
        if self._teacher_task and not self._teacher_task.done():
            self._teacher_task.cancel()
        self._teacher_task = asyncio.create_task(
            self._teacher.analyze_move(fen, move_uci)
        )

    # ── Public API ────────────────────────────────────────────────────

    async def start_game(self, fen: Optional[str] = None) -> None:
        """Start a new game, optionally from a given FEN position.

        Args:
            fen: Optional FEN string to start from. If None, starts from the
                 standard opening position.
        """
        if fen:
            valid, err = self._validate_fen(fen)
            if not valid:
                logger.error(f"Cannot start game — invalid FEN: {err}")
                logger.error(f"  Rejected FEN: {fen}")
                return
            self._board.set_fen(fen)
            logger.info(f"Game started from custom FEN: {fen}")
        else:
            self._board.reset()
            logger.info("Game started from standard position.")

        self._move_history.clear()

        # Determine whose turn it is from the board position
        if (self._human_color == PlayerColor.WHITE and self._board.turn == chess.WHITE) or \
           (self._human_color == PlayerColor.BLACK and self._board.turn == chess.BLACK):
            self._transition(GameState.HUMAN_TURN)
        else:
            self._transition(GameState.AGENT_TURN)

    async def reset(self) -> None:
        """Reset to waiting state."""
        self._board.reset()
        self._move_history.clear()
        self._transition(GameState.WAITING)

    # ── Main Game Loop ────────────────────────────────────────────────

    async def run_game_loop(self) -> None:
        """Main game loop — runs as an asyncio task.

        Checks the current state and calls the appropriate handler.
        Loops until GAME_OVER or shutdown signal.
        """
        logger.info("Game loop started.")
        while self._state != GameState.GAME_OVER and not self._shutdown.is_set():
            if self._state == GameState.HUMAN_TURN:
                await self._handle_human_turn()
            elif self._state == GameState.AGENT_TURN:
                await self._handle_agent_turn()
            else:
                # WAITING or intermediate states — just idle
                await asyncio.sleep(0.1)

        if self._board.is_game_over():
            result = self._board.result()
            logger.info(f"Game over: {result}")
            outcome = self._board.outcome()
            if outcome:
                if outcome.winner is None:
                    logger.info("Draw!")
                elif outcome.winner == chess.WHITE:
                    logger.info("White wins!")
                else:
                    logger.info("Black wins!")

        logger.info("Game loop ended.")

    # ── Human Turn Handling ───────────────────────────────────────────

    async def _handle_human_turn(self) -> None:
        """Wait for human move from CLI queue, voice, or perception trigger."""
        # Start voice listening if enabled and not already running (pushes to same queue)
        if self._voice_in and not self._voice_in.is_listening:
            await self._voice_in.start_listening(self.board_fen)

        try:
            # Wait for move with a timeout so we can check shutdown
            move_uci = await asyncio.wait_for(
                self._human_move_queue.get(), timeout=0.5
            )
        except asyncio.TimeoutError:
            return  # No move yet, loop again

        # Stop voice listening once we have a move
        if self._voice_in:
            logger.debug(f"[VoiceIn] Stopping STT listener (received move: {move_uci})")
            self._voice_in.stop_listening()

        if move_uci == "__capture__":
            # Trigger perception with automatic retry on invalid FEN
            for attempt in range(1, _MAX_CAPTURE_RETRIES + 1):
                accepted = await self._detect_human_move()
                if accepted:
                    break
                if attempt < _MAX_CAPTURE_RETRIES:
                    logger.warning(
                        f"Perception attempt {attempt}/{_MAX_CAPTURE_RETRIES} failed. "
                        f"Retrying capture..."
                    )
                    await asyncio.sleep(0.5)  # brief delay before retry
                else:
                    logger.error(
                        f"Perception failed after {_MAX_CAPTURE_RETRIES} attempts. "
                        f"Returning to HUMAN_TURN — try again manually."
                    )
                    return  # Stay in HUMAN_TURN

            # Board was already updated by _detect_human_move.
            # Perception means the human already physically moved the piece,
            # so no robot execution needed.
            if self._board.is_game_over():
                self._transition(GameState.GAME_OVER)
            else:
                self._transition(GameState.AGENT_TURN)
            return

        # Voice or CLI move — robot must physically execute it on the board
        await self._apply_human_move(move_uci, execute_on_robot=True)

    async def _apply_human_move(
        self, move_uci: str, execute_on_robot: bool = False
    ) -> bool:
        """Validate and apply a human move.

        Args:
            move_uci: Move in UCI notation.
            execute_on_robot: If True, send the move to the robot arm before
                updating the internal board. This is used for voice/CLI moves
                where the human has not physically moved the piece.
        """
        self._transition(GameState.VALIDATING)

        try:
            move = chess.Move.from_uci(move_uci)
            if move not in self._board.legal_moves:
                logger.warning(f"Illegal move: {move_uci}")
                # Let the teacher explain why the move is illegal (speaks via TTS)
                if self._teacher and self._config.teacher.enabled:
                    self._launch_teacher(self._board.fen(), move_uci)
                self._transition(GameState.HUMAN_TURN)
                return False

            # Execute on robot BEFORE updating internal board (robot needs
            # the pre-move board state to know piece positions)
            if execute_on_robot and not self._config.simulation_mode:
                self._transition(GameState.EXECUTING)
                logger.info(f"Executing human voice/CLI move on robot: {move_uci}")
                result = await self._execute_robot_move(move_uci)
                if not result.success:
                    logger.error(f"Robot failed to execute human move: {result.error}")
                    # Still apply the move logically — robot failure shouldn't
                    # block the game, but log prominently
                else:
                    logger.info(
                        f"Robot executed human move {move_uci} "
                        f"({result.execution_time_sec:.1f}s)"
                    )

            # Capture FEN before push for teacher analysis
            fen_before = self._board.fen()

            san = self._board.san(move)
            self._board.push(move)
            self._move_history.append(move_uci)
            logger.info(f"Human played: {move_uci} ({san})")
            self._print_board_status("after human move")

            # Fire teacher analysis as background task
            if self._teacher and self._config.teacher.enabled:
                logger.debug(f"[Teacher] Launching background analysis for {move_uci}")
                self._launch_teacher(fen_before, move_uci)

            if self._board.is_game_over():
                self._transition(GameState.GAME_OVER)
            else:
                self._transition(GameState.AGENT_TURN)
            return True

        except ValueError:
            logger.error(f"Invalid UCI move: {move_uci}")
            # Let the teacher explain the invalid move if possible
            if self._teacher and self._config.teacher.enabled:
                self._launch_teacher(self._board.fen(), move_uci)
            self._transition(GameState.HUMAN_TURN)
            return False

    # ── Agent Turn Handling ───────────────────────────────────────────

    async def _handle_agent_turn(self) -> None:
        """Trigger agent deliberation, get move, execute on robot."""
        self._transition(GameState.THINKING)

        # Request agent move with retry on illegal/invalid results
        decision = None
        move = None
        move_uci = ""
        for attempt in range(1, _MAX_AGENT_RETRIES + 1):
            decision = await self._request_agent_move()
            if not decision or not decision.selected_move_uci:
                logger.error(
                    f"Agent failed to produce a move (attempt {attempt}/{_MAX_AGENT_RETRIES})."
                )
                if attempt < _MAX_AGENT_RETRIES:
                    await asyncio.sleep(1.0)
                continue

            move_uci = decision.selected_move_uci
            try:
                move = chess.Move.from_uci(move_uci)
                if move not in self._board.legal_moves:
                    logger.error(
                        f"Agent returned illegal move: {move_uci} "
                        f"(attempt {attempt}/{_MAX_AGENT_RETRIES})"
                    )
                    move = None
                    if attempt < _MAX_AGENT_RETRIES:
                        await asyncio.sleep(1.0)
                    continue
            except ValueError:
                logger.error(
                    f"Agent returned invalid UCI: {move_uci} "
                    f"(attempt {attempt}/{_MAX_AGENT_RETRIES})"
                )
                move = None
                if attempt < _MAX_AGENT_RETRIES:
                    await asyncio.sleep(1.0)
                continue
            break  # valid move found

        if not decision or not move:
            logger.error(
                f"Agent failed after {_MAX_AGENT_RETRIES} attempts. Returning to WAITING."
            )
            self._transition(GameState.WAITING)
            return

        # Filter to opinions that voted for the winning move, capped to
        # max_opinions_to_speak.  The same list is sent to the frontend AND
        # spoken via TTS so the displayed opinion always matches the voice.
        winning_opinions = [
            op for op in decision.opinions
            if op.proposed_move == move_uci
        ]
        # Fall back to all opinions if none match (e.g. supervisor-only)
        display_opinions = winning_opinions or decision.opinions
        display_opinions = display_opinions[: self._config.voice.max_opinions_to_speak]

        logger.info(
            f"Agent proposed move: {move_uci} — "
            f"{len(winning_opinions)} winning opinion(s) / "
            f"{len(decision.opinions)} total, displaying {len(display_opinions)}"
        )

        # Emit agent opinions event (frontend shows the same opinions as TTS)
        self._emit_event(
            GameStateEvent(
                event_type="agent_deliberation",
                data={
                    "selected_move": move_uci,
                    "voting_summary": decision.voting_summary,
                    "opinions": [
                        {
                            "piece_type": op.piece_type,
                            "proposed_move": op.proposed_move,
                            "reasoning": op.reasoning,
                        }
                        for op in display_opinions
                    ],
                },
            )
        )

        # Execute on robot + speak agent opinions in parallel
        self._transition(GameState.EXECUTING)

        voice_tasks = []
        if (
            self._voice_out
            and self._config.voice.enabled
            and self._config.voice.speak_agent_opinions
        ):
            for op in display_opinions:
                logger.debug(f"[VoiceOut]   {op.piece_type}: {op.reasoning[:60]}...")
                voice_tasks.append(
                    self._voice_out.speak(op.reasoning, op.piece_type)
                )

        if self._config.game.parallel_robot_voice:
            # Run robot + voice in parallel
            tasks = []
            if not self._config.simulation_mode:
                tasks.append(self._execute_robot_move(move_uci))
            tasks.extend(voice_tasks)
            robot_count = 0 if self._config.simulation_mode else 1
            logger.debug(
                f"[Parallel] Launching {len(tasks)} task(s): "
                f"{robot_count} robot + {len(voice_tasks)} voice"
            )
            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                # Check robot result (first task when not in simulation mode)
                if not self._config.simulation_mode:
                    robot_result = results[0]
                    if isinstance(robot_result, MoveResult) and not robot_result.success:
                        logger.error(f"Robot execution failed: {robot_result.error}")
                    elif isinstance(robot_result, Exception):
                        logger.error(f"Robot execution error: {robot_result}")
                # Log any voice errors
                voice_start = 0 if self._config.simulation_mode else 1
                for i, r in enumerate(results[voice_start:], start=voice_start):
                    if isinstance(r, Exception):
                        logger.error(f"Voice task {i} error: {r}")
            else:
                logger.info(f"Simulation mode: skipping robot execution for {move_uci}")
        else:
            # Sequential: robot first, then voice
            if not self._config.simulation_mode:
                result = await self._execute_robot_move(move_uci)
                if not result.success:
                    logger.error(f"Robot execution failed: {result.error}")
            else:
                logger.info(f"Simulation mode: skipping robot execution for {move_uci}")
            for vt in voice_tasks:
                await vt

        # Apply move to internal board
        san = self._board.san(move)
        self._board.push(move)
        self._move_history.append(move_uci)
        logger.info(f"Agent played: {move_uci} ({san})")

        if self._board.is_game_over():
            self._transition(GameState.GAME_OVER)
        else:
            self._transition(GameState.HUMAN_TURN)

    async def _request_agent_move(self) -> Optional[AgentDecision]:
        """Request a move from the agent backend via ROS2 bridge."""
        if not self._bridge:
            logger.error("No bridge client configured for agent.")
            return None

        if not self._bridge.is_connected:
            logger.error("Bridge not connected. Cannot request agent move.")
            return None

        # Subscribe to result topic BEFORE publishing to avoid race
        self._bridge._ensure_subscribed("/chess/agent_opinions")

        # Build and publish agent request
        strategy = self._config.game.agent_strategy
        request_data = {
            "fen": self.board_fen,
            "strategy": strategy,
        }

        logger.info(f"Requesting agent move via ROS: strategy={strategy}")
        sent = await self._bridge.publish("/chess/agent_request", request_data)
        if not sent:
            logger.error("Failed to send agent request (bridge disconnected).")
            return None

        # Wait for agent response
        msg = await self._bridge.wait_for_message(
            "/chess/agent_opinions",
            timeout=self._config.agent_timeout_sec,
        )
        if not msg:
            logger.error("Agent timeout — no response received.")
            return None

        # Parse response into AgentDecision
        data = msg.data
        agent_color = "white" if " w " in self.board_fen else "black"

        opinions = []
        for op_data in data.get("opinions", []):
            opinions.append(
                AgentOpinion(
                    piece_type=op_data.get("piece_type") or None,
                    piece_color=op_data.get("piece_color", agent_color),
                    proposed_move=op_data.get("proposed_move", ""),
                    reasoning=op_data.get("reasoning", ""),
                    confidence=float(op_data.get("confidence", 0.0)),
                    vote_weight=int(op_data.get("vote_weight", 1)),
                )
            )

        decision = AgentDecision(
            opinions=opinions,
            selected_move_uci=data.get("selected_move_uci", ""),
            selected_move_san=data.get("selected_move_san", ""),
            vote_confidence=float(data.get("vote_confidence", 0.0)),
            voting_summary=data.get("voting_summary", ""),
        )

        logger.info(f"Agent selected move: {decision.selected_move_uci}")
        logger.debug(f"Deliberation summary: {decision.voting_summary}")
        return decision

    # ── Board Status ─────────────────────────────────────────────────

    def _print_board_status(self, context: str = "") -> None:
        """Print the current board state for debugging."""
        header = f"Board status ({context})" if context else "Board status"
        turn = "White" if self._board.turn == chess.WHITE else "Black"
        check = " (CHECK)" if self._board.is_check() else ""
        logger.info(
            f"\n{'=' * 40}\n"
            f"  {header}\n"
            f"  FEN: {self._board.fen()}\n"
            f"  Turn: {turn}{check}\n"
            f"  Moves: {len(self._move_history)}\n"
            f"  Legal moves: {self._board.legal_moves.count()}\n"
            f"\n{self._board.unicode()}\n"
            f"{'=' * 40}"
        )

    # ── FEN Validation ─────────────────────────────────────────────────

    @staticmethod
    def _validate_fen(fen: str) -> tuple[bool, str]:
        """Validate that a FEN string represents a legal chess position.

        Returns (is_valid, error_message).
        """
        try:
            board = chess.Board(fen)
        except ValueError as e:
            return False, f"Invalid FEN syntax: {e}"

        # Check king counts
        white_kings = len(board.pieces(chess.KING, chess.WHITE))
        black_kings = len(board.pieces(chess.KING, chess.BLACK))
        if white_kings != 1:
            return False, f"Expected 1 white king, found {white_kings}"
        if black_kings != 1:
            return False, f"Expected 1 black king, found {black_kings}"

        # Check the position is not obviously illegal
        if not board.is_valid():
            return False, f"Invalid position: {board.status()}"

        return True, ""

    # ── Perception Integration ────────────────────────────────────────

    async def _detect_human_move(self) -> bool:
        """Trigger perception and accept any result with success=True.

        Sets the internal board to the detected FEN directly, bypassing
        legal move validation. Returns True if the board was updated.
        """
        if not self._bridge:
            logger.error("No bridge client configured for perception.")
            return False

        if not self._bridge.is_connected:
            logger.error("Bridge not connected. Cannot trigger perception.")
            return False

        # Subscribe to result topic BEFORE publishing trigger to avoid race
        self._bridge._ensure_subscribed("/chess/perception_result")

        # Publish capture trigger
        logger.info("Triggering perception capture...")
        sent = await self._bridge.publish("/chess/capture", {})
        if not sent:
            logger.error("Failed to send capture trigger (bridge disconnected).")
            return False

        # Wait for perception result
        msg = await self._bridge.wait_for_message(
            "/chess/perception_result",
            timeout=self._config.perception_timeout_sec,
        )
        if not msg:
            logger.error("Perception timeout — no result received.")
            return False

        if not msg.data.get("success", False):
            logger.error(f"Perception returned success=False: {msg.data.get('error', '')}")
            return False

        detected_fen = msg.data.get("fen", "")
        if not detected_fen:
            logger.error("Perception returned empty FEN.")
            return False

        logger.info(f"Perception detected FEN: {detected_fen}")

        # Validate the FEN before doing anything with it
        valid, err = self._validate_fen(detected_fen)
        if not valid:
            logger.error(f"Perception returned invalid FEN: {err}")
            logger.error(f"  Rejected FEN: {detected_fen}")
            self._print_board_status("after invalid perception — board unchanged")
            return False

        self._print_board_status("perception received — before applying")

        # Try to identify the move via board diff (best-effort, for move history)
        matched = self._match_move_to_fen(detected_fen)
        if matched:
            logger.info(f"Perception matched legal move: {matched}")
            san = self._board.san(chess.Move.from_uci(matched))
            self._board.push(chess.Move.from_uci(matched))
            self._move_history.append(matched)
            logger.info(f"Human played: {matched} ({san})")
        else:
            # No legal move matched — accept the FEN directly anyway
            logger.warning(
                "Perception FEN doesn't match any legal move. "
                "Accepting detected position directly."
            )
            self._board.set_fen(detected_fen)
            self._move_history.append(f"fen:{detected_fen.split()[0]}")
            logger.info(f"Board set to detected FEN: {detected_fen}")

        self._print_board_status("after human move applied")
        return True

    def _match_move_to_fen(self, detected_fen: str) -> Optional[str]:
        """Find which legal move produces a position matching detected_fen.

        Compares piece placement only (first field of FEN) to be robust
        against differences in castling rights, en passant, etc.
        """
        detected_placement = detected_fen.split()[0]
        for move in self._board.legal_moves:
            self._board.push(move)
            candidate = self._board.fen().split()[0]
            self._board.pop()
            if candidate == detected_placement:
                return move.uci()
        return None

    # ── Robot Move Execution ──────────────────────────────────────────

    async def _execute_robot_move(self, move_uci: str) -> MoveResult:
        """Send move to robot via ROS2 bridge and wait for result."""
        if not self._bridge:
            return MoveResult(move_uci=move_uci, success=False, error="No bridge client")

        if not self._bridge.is_connected:
            return MoveResult(move_uci=move_uci, success=False, error="Bridge not connected")

        move = chess.Move.from_uci(move_uci)
        piece = self._board.piece_at(move.from_square)

        # Build MoveCommand dict (pattern from orchestrator.send_to_robot)
        is_capture = self._board.is_capture(move)
        captured_piece = None
        if is_capture:
            captured = self._board.piece_at(move.to_square)
            if captured:
                captured_piece = _PIECE_TYPE_MAP.get(captured.piece_type)
            elif self._board.is_en_passant(move):
                captured_piece = "pawn"

        is_castling = self._board.is_castling(move)
        is_en_passant = self._board.is_en_passant(move)
        is_promotion = move.promotion is not None
        promotion_piece = None
        if is_promotion and move.promotion:
            promotion_piece = _PIECE_TYPE_MAP.get(move.promotion)

        castling_type = ""
        if is_castling:
            castling_type = "kingside" if chess.square_file(move.to_square) > chess.square_file(move.from_square) else "queenside"

        command = {
            "move_uci": move_uci,
            "from_square": chess.square_name(move.from_square),
            "to_square": chess.square_name(move.to_square),
            "piece_type": _PIECE_TYPE_MAP.get(piece.piece_type, "unknown") if piece else "unknown",
            "piece_color": "white" if piece and piece.color == chess.WHITE else "black",
            "is_capture": is_capture,
            "captured_piece": captured_piece or "",
            "is_castling": is_castling,
            "castling_type": castling_type,
            "is_en_passant": is_en_passant,
            "is_promotion": is_promotion,
            "promotion_piece": promotion_piece or "",
            "board_fen": self._board.fen(),
        }

        # Subscribe to result topic BEFORE publishing trigger to avoid race
        self._bridge._ensure_subscribed("/chess/move_result")

        logger.info(f"Sending move to robot: {move_uci}")
        sent = await self._bridge.publish("/chess/move_request", command)
        if not sent:
            return MoveResult(move_uci=move_uci, success=False, error="Failed to send move (bridge disconnected)")

        # Wait for robot result
        msg = await self._bridge.wait_for_message(
            "/chess/move_result",
            timeout=self._config.robot_timeout_sec,
        )
        if not msg:
            return MoveResult(move_uci=move_uci, success=False, error="Robot timeout")

        return MoveResult(
            move_uci=msg.data.get("move_uci", move_uci),
            success=msg.data.get("success", False),
            error=msg.data.get("error", ""),
            execution_time_sec=msg.data.get("execution_time_sec", 0.0),
        )

    # ── Legacy compatibility ──────────────────────────────────────────

    async def on_human_move_detected(self, move_uci: str) -> bool:
        """Process a detected human move (from perception or voice).

        Returns True if the move was valid and applied.
        This is the direct-call API; the game loop uses _human_move_queue instead.
        """
        return await self._apply_human_move(move_uci)

    def is_human_turn(self) -> bool:
        """Check if it's the human's turn based on board state."""
        if self._human_color == PlayerColor.WHITE:
            return self._board.turn == chess.WHITE
        return self._board.turn == chess.BLACK
