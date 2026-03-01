"""Main orchestrator for coordinating game sessions and agents."""

import asyncio
import time
from typing import AsyncIterator

from backend.chess_engine import ChessBoard
from backend.core import get_logger
from backend.llm import get_provider

from backend.agents.personality import load_personality_preset, PERSONALITY_PRESETS
from backend.agents.strategies import (
    DecisionStrategy,
    DemocraticStrategy,
    SupervisorStrategy,
    HybridStrategy,
)
from backend.agents.strategies.base import DecisionResult, DeliberationEvent

from .session import GameSession, GameState

logger = get_logger(__name__)


class Orchestrator:
    """
    Main orchestrator that coordinates game sessions and agent interactions.

    Responsibilities:
    - Manage active game sessions
    - Route requests to appropriate strategies
    - Handle move generation and validation
    - Emit events for real-time updates

    Supports separate model configuration for supervisor (reasoning model)
    and piece agents (smaller, faster model).
    """

    # Available Mistral models
    AVAILABLE_MODELS = [
        "mistral-small-latest",
        "mistral-medium-latest",
        "mistral-large-latest",
        "codestral-latest",
        "ministral-3b-latest",
        "ministral-8b-latest",
    ]

    DEFAULT_SUPERVISOR_MODEL = "mistral-medium-latest"
    DEFAULT_AGENT_MODEL = "mistral-small-latest"

    def __init__(
        self,
        provider_name: str = "mistral",
        personality_preset: str = "default",
        supervisor_model: str | None = None,
        agent_model: str | None = None,
    ):
        self._sessions: dict[str, GameSession] = {}
        self._provider_name = provider_name
        self._supervisor_model = supervisor_model or self.DEFAULT_SUPERVISOR_MODEL
        self._agent_model = agent_model or self.DEFAULT_AGENT_MODEL
        self._personality_preset = personality_preset
        self._personality_overrides = load_personality_preset(personality_preset)
        self._strategies: dict[str, DecisionStrategy] = {}
        self._initialize_strategies()

    def _initialize_strategies(self) -> None:
        """Initialize available decision strategies with separate models for supervisor and agents."""
        from backend.agents.base import AgentConfig

        # Create separate configs for supervisor (reasoning model) and agents
        agent_config = AgentConfig(
            agent_id="agent",
            llm_provider=self._provider_name,
            llm_model=self._agent_model,
        )

        supervisor_config = AgentConfig(
            agent_id="supervisor",
            llm_provider=self._provider_name,
            llm_model=self._supervisor_model,
        )

        self._strategies = {
            "democratic": DemocraticStrategy(
                provider_name=self._provider_name,
                agent_config=agent_config,
            ),
            "supervisor": SupervisorStrategy(
                provider_name=self._provider_name,
                agent_config=agent_config,
                supervisor_config=supervisor_config,
            ),
            "hybrid": HybridStrategy(
                provider_name=self._provider_name,
                agent_config=agent_config,
                supervisor_config=supervisor_config,
                personality_overrides=self._personality_overrides,
            ),
        }

    def get_supervisor_model(self) -> str:
        """Get the current supervisor LLM model."""
        return self._supervisor_model

    def get_agent_model(self) -> str:
        """Get the current agent LLM model."""
        return self._agent_model

    def set_supervisor_model(self, model: str) -> None:
        """Set the LLM model for the supervisor (reasoning model)."""
        if model not in self.AVAILABLE_MODELS:
            raise ValueError(f"Unknown model: {model}. Available: {self.AVAILABLE_MODELS}")

        self._supervisor_model = model
        self._initialize_strategies()
        logger.info(f"Changed supervisor model to: {model}")

    def set_agent_model(self, model: str) -> None:
        """Set the LLM model for piece agents."""
        if model not in self.AVAILABLE_MODELS:
            raise ValueError(f"Unknown model: {model}. Available: {self.AVAILABLE_MODELS}")

        self._agent_model = model
        self._initialize_strategies()
        logger.info(f"Changed agent model to: {model}")

    def list_llm_models(self) -> list[str]:
        """List available LLM models."""
        return self.AVAILABLE_MODELS

    def set_personality_preset(self, preset_name: str) -> None:
        """Change the personality preset for all strategies."""
        if preset_name not in PERSONALITY_PRESETS:
            raise ValueError(f"Unknown preset: {preset_name}. Available: {PERSONALITY_PRESETS}")

        self._personality_preset = preset_name
        self._personality_overrides = load_personality_preset(preset_name)

        # Reinitialize strategies with new personalities
        self._initialize_strategies()
        logger.info(f"Changed personality preset to: {preset_name}")

    def get_personality_preset(self) -> str:
        """Get the current personality preset name."""
        return self._personality_preset

    def list_personality_presets(self) -> list[str]:
        """List available personality presets."""
        return PERSONALITY_PRESETS

    def get_personality_overrides(self) -> dict[str, dict[str, float]]:
        """Get current personality overrides for all pieces."""
        return self._personality_overrides

    def set_piece_personality(self, piece_type: str, weights: dict[str, float]) -> None:
        """Set personality weights for a specific piece type."""
        valid_pieces = ["pawn", "knight", "bishop", "rook", "queen", "king"]
        if piece_type not in valid_pieces:
            raise ValueError(f"Unknown piece type: {piece_type}. Valid: {valid_pieces}")

        valid_traits = [
            "self_preservation", "personal_glory", "team_victory",
            "aggression", "positional_dominance", "cooperation"
        ]

        # Validate and clamp weights
        validated_weights = {}
        for trait, value in weights.items():
            if trait in valid_traits:
                validated_weights[trait] = max(0.0, min(1.0, float(value)))

        self._personality_overrides[piece_type] = {
            **self._personality_overrides.get(piece_type, {}),
            **validated_weights
        }

        # Mark preset as custom
        self._personality_preset = "custom"

        # Reinitialize strategies with new personalities
        self._initialize_strategies()
        logger.info(f"Updated personality for {piece_type}: {validated_weights}")

    def get_strategy(self, name: str) -> DecisionStrategy:
        """Get a strategy by name."""
        if name not in self._strategies:
            raise ValueError(f"Unknown strategy: {name}")
        return self._strategies[name]

    def list_strategies(self) -> list[str]:
        """List available strategy names."""
        return list(self._strategies.keys())

    # Session Management

    def create_session(
        self,
        fen: str | None = None,
        strategy: str = "hybrid",
        white_player: str = "human",
        black_player: str = "agent",
        **config,
    ) -> GameSession:
        """Create a new game session."""
        if fen:
            session = GameSession.from_fen(
                fen,
                strategy=strategy,
                white_player=white_player,
                black_player=black_player,
                config=config,
            )
        else:
            session = GameSession(
                strategy=strategy,
                white_player=white_player,
                black_player=black_player,
                config=config,
            )

        self._sessions[session.id] = session
        logger.info(f"Created game session {session.id}")
        return session

    def get_session(self, session_id: str) -> GameSession | None:
        """Get a session by ID."""
        return self._sessions.get(session_id)

    def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        if session_id in self._sessions:
            del self._sessions[session_id]
            logger.info(f"Deleted game session {session_id}")
            return True
        return False

    def list_sessions(self) -> list[GameSession]:
        """List all active sessions."""
        return list(self._sessions.values())

    # Move Operations

    async def make_player_move(
        self, session_id: str, move: str
    ) -> tuple[GameSession, dict]:
        """
        Process a player move.

        Returns the updated session and move info.
        """
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")

        if session.state != GameState.ACTIVE:
            raise ValueError(f"Game is not active: {session.state}")

        if session.is_agent_turn:
            raise ValueError("It's the agent's turn")

        # Validate and make move
        fen_before = session.board.fen
        if not session.board.is_legal_move(move):
            raise ValueError(f"Illegal move: {move}")

        move_info = session.board.make_move(move)
        fen_after = session.board.fen

        # Record the move
        record = session.record_move(
            move=move,
            san=move_info.san,
            fen_before=fen_before,
            fen_after=fen_after,
        )

        return session, {
            "move": move,
            "san": move_info.san,
            "fen": fen_after,
            "is_check": move_info.is_check,
            "is_checkmate": move_info.is_checkmate,
            "is_game_over": session.is_game_over,
            "result": session.result,
        }

    async def generate_agent_move(
        self, session_id: str
    ) -> tuple[GameSession, DecisionResult]:
        """
        Generate an agent move for the given session.

        Returns the session and the decision result with all deliberation info.
        """
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")

        if session.state != GameState.ACTIVE:
            raise ValueError(f"Game is not active: {session.state}")

        if not session.is_agent_turn:
            raise ValueError("It's the player's turn")

        start_time = time.time()

        # Get strategy and generate move
        strategy = self.get_strategy(session.strategy)
        result = await strategy.decide(session.board)

        time_taken_ms = (time.time() - start_time) * 1000

        # Make the move
        fen_before = session.board.fen
        move_info = session.board.make_move(result.selected_move)
        fen_after = session.board.fen

        # Record the move
        session.record_move(
            move=result.selected_move,
            san=move_info.san,
            fen_before=fen_before,
            fen_after=fen_after,
            proposals=result.proposals,
            deliberation_summary=result.deliberation_summary,
            time_taken_ms=time_taken_ms,
        )

        return session, result

    async def stream_agent_move(
        self, session_id: str
    ) -> AsyncIterator[DeliberationEvent]:
        """
        Stream the agent move generation process.

        Yields deliberation events as the agent thinks.
        """
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")

        if session.state != GameState.ACTIVE:
            raise ValueError(f"Game is not active: {session.state}")

        if not session.is_agent_turn:
            raise ValueError("It's the player's turn")

        strategy = self.get_strategy(session.strategy)
        start_time = time.time()
        final_move = None

        logger.info(f"Starting agent deliberation with strategy: {session.strategy}")

        try:
            async for event in strategy.stream_deliberation(session.board):
                logger.debug(f"Deliberation event: {event.event_type}")
                yield event

                # Capture final move from deliberation_complete event
                if event.event_type == "deliberation_complete":
                    final_move = event.data.get("selected_move")

            # Make the move if we have one
            if final_move:
                time_taken_ms = (time.time() - start_time) * 1000
                fen_before = session.board.fen
                move_info = session.board.make_move(final_move)
                fen_after = session.board.fen

                session.record_move(
                    move=final_move,
                    san=move_info.san,
                    fen_before=fen_before,
                    fen_after=fen_after,
                    time_taken_ms=time_taken_ms,
                )

                yield DeliberationEvent(
                    event_type="agent_move",
                    agent_id="system",
                    data={
                        "move": final_move,
                        "san": move_info.san,
                        "fen": fen_after,
                        "is_check": move_info.is_check,
                        "is_checkmate": move_info.is_checkmate,
                        "is_game_over": session.is_game_over,
                        "result": session.result,
                    },
                )
        except Exception as e:
            logger.error(f"Error during agent deliberation: {e}", exc_info=True)
            yield DeliberationEvent(
                event_type="error",
                agent_id="system",
                data={"message": str(e)},
            )

    # External API for move generation

    async def generate_move_for_position(
        self, fen: str, strategy: str = "hybrid"
    ) -> DecisionResult:
        """
        Generate a move for an arbitrary position (external API).

        This doesn't require a session - useful for one-off move generation.
        """
        board = ChessBoard.from_fen(fen)
        strat = self.get_strategy(strategy)
        return await strat.decide(board)

    async def stream_move_for_position(
        self, fen: str, strategy: str = "hybrid"
    ) -> AsyncIterator[DeliberationEvent]:
        """
        Stream move generation for an arbitrary position (external API).
        """
        board = ChessBoard.from_fen(fen)
        strat = self.get_strategy(strategy)
        async for event in strat.stream_deliberation(board):
            yield event

    # External Hardware Integration

    async def request_detection(self, session_id: str) -> "DetectionResult":
        """
        Request board state capture from the detection system.

        Updates the session with the detected position.
        """
        from backend.external import DetectionResult, get_external_manager

        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")

        manager = get_external_manager()
        result = await manager.detection_client.capture()

        if result.success and result.fen:
            # Update session with detected position
            session.last_detection_fen = result.fen
            session.detected_pieces = result.pieces

            # Update the board to match detected position
            session.board = ChessBoard.from_fen(result.fen)
            logger.info(f"Updated session {session_id} board from detection: {result.fen}")

        return result

    async def send_to_robot(
        self, session_id: str, move: str, board_fen: str | None = None
    ) -> "RobotResult":
        """
        Send a move command to the robot system.

        Args:
            session_id: The game session ID.
            move: The move in UCI notation (e.g., "e2e4").
            board_fen: Optional FEN for context. If not provided, uses session board.
        """
        from backend.external import MoveCommand, RobotResult, get_external_manager
        import chess

        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")

        manager = get_external_manager()

        # Parse move details
        fen = board_fen or session.board.fen
        board = chess.Board(fen)

        try:
            chess_move = chess.Move.from_uci(move)
        except ValueError:
            return RobotResult(success=False, error=f"Invalid move format: {move}")

        if chess_move not in board.legal_moves:
            return RobotResult(success=False, error=f"Illegal move: {move}")

        # Get piece info
        from_square = chess.square_name(chess_move.from_square)
        to_square = chess.square_name(chess_move.to_square)
        piece = board.piece_at(chess_move.from_square)

        if not piece:
            return RobotResult(success=False, error=f"No piece at {from_square}")

        piece_type_map = {
            chess.PAWN: "pawn",
            chess.KNIGHT: "knight",
            chess.BISHOP: "bishop",
            chess.ROOK: "rook",
            chess.QUEEN: "queen",
            chess.KING: "king",
        }

        # Check for special moves
        is_capture = board.is_capture(chess_move)
        captured_piece = None
        if is_capture:
            captured = board.piece_at(chess_move.to_square)
            if captured:
                captured_piece = piece_type_map.get(captured.piece_type)
            elif board.is_en_passant(chess_move):
                captured_piece = "pawn"

        is_castling = board.is_castling(chess_move)
        is_en_passant = board.is_en_passant(chess_move)
        is_promotion = chess_move.promotion is not None
        promotion_piece = None
        if is_promotion and chess_move.promotion:
            promotion_piece = piece_type_map.get(chess_move.promotion)

        command = MoveCommand(
            move=move,
            from_square=from_square,
            to_square=to_square,
            piece_type=piece_type_map.get(piece.piece_type, "unknown"),
            piece_color="white" if piece.color == chess.WHITE else "black",
            is_capture=is_capture,
            captured_piece=captured_piece,
            is_castling=is_castling,
            is_en_passant=is_en_passant,
            is_promotion=is_promotion,
            promotion_piece=promotion_piece,
            board_fen=fen,
        )

        result = await manager.robot_client.execute_move(command)
        logger.info(f"Robot execution for move {move}: success={result.success}")

        return result

    async def real_mode_turn(
        self, session_id: str
    ) -> AsyncIterator[DeliberationEvent]:
        """
        Execute a full real-mode turn: detect → agent deliberation → robot execution.

        Yields events throughout the process for real-time UI updates.
        """
        from backend.external import get_external_manager

        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")

        if session.state != GameState.ACTIVE:
            raise ValueError(f"Game is not active: {session.state}")

        manager = get_external_manager()

        # Step 1: Detection
        yield DeliberationEvent(
            event_type="detection_started",
            agent_id="system",
            data={},
        )

        detection_result = await self.request_detection(session_id)

        yield DeliberationEvent(
            event_type="detection_complete",
            agent_id="system",
            data={
                "success": detection_result.success,
                "fen": detection_result.fen,
                "pieces": detection_result.pieces,
                "error": detection_result.error,
            },
        )

        if not detection_result.success:
            yield DeliberationEvent(
                event_type="error",
                agent_id="system",
                data={"message": f"Detection failed: {detection_result.error}"},
            )
            return

        # Ensure the board turn matches the agent's color.
        # Detection only sees pieces — it doesn't know whose turn it is.
        # In real mode the human just moved, so it must be the agent's turn.
        import chess as chess_lib

        if session.black_player == "agent":
            session.board._board.turn = chess_lib.BLACK
        else:
            session.board._board.turn = chess_lib.WHITE

        # Step 2: Agent deliberation (stream all events)
        final_move = None
        move_san = None

        async for event in self.stream_agent_move(session_id):
            yield event

            # Capture the final move from agent_move event
            if event.event_type == "agent_move":
                final_move = event.data.get("move")
                move_san = event.data.get("san")

        if not final_move:
            yield DeliberationEvent(
                event_type="error",
                agent_id="system",
                data={"message": "No move generated by agent"},
            )
            return

        # Step 3: Robot execution
        yield DeliberationEvent(
            event_type="robot_executing",
            agent_id="system",
            data={"move": final_move, "san": move_san},
        )

        # Use the FEN before the move was made (we need to get it from the board history)
        # Since the move was already made in stream_agent_move, we need the pre-move FEN
        # which is stored in the last move record
        pre_move_fen = None
        if session.moves:
            pre_move_fen = session.moves[-1].fen_before

        robot_result = await self.send_to_robot(
            session_id, final_move, board_fen=pre_move_fen
        )

        yield DeliberationEvent(
            event_type="robot_complete",
            agent_id="system",
            data={
                "success": robot_result.success,
                "error": robot_result.error,
                "move": final_move,
                "san": move_san,
            },
        )


# Global orchestrator instance
_orchestrator: Orchestrator | None = None


def get_orchestrator() -> Orchestrator:
    """Get the global orchestrator instance."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator()
    return _orchestrator
