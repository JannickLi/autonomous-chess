"""Stockfish chess engine analyzer for position analysis and threat detection."""

import asyncio
import shutil
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import chess
import chess.engine

if TYPE_CHECKING:
    from .board import ChessBoard


@dataclass
class MoveAnalysis:
    """Analysis of a single move from the engine."""

    uci: str  # "e2e4"
    san: str  # "e4"
    centipawn_score: int | None  # +50 = 0.5 pawn advantage
    mate_in: int | None  # Mate in N moves (None if not a mate)
    is_capture: bool
    is_check: bool
    captured_piece: str | None  # "knight", "pawn", etc.


@dataclass
class PieceStatus:
    """Status of a piece including attack/defense information."""

    piece_type: str  # "knight"
    square: str  # "f3"
    is_attacked: bool
    is_defended: bool
    is_hanging: bool  # attacked but not defended
    attackers: list[str] = field(default_factory=list)  # ["bishop_c5", "pawn_e4"]
    defenders: list[str] = field(default_factory=list)


@dataclass
class PositionAnalysis:
    """Complete analysis of a chess position."""

    top_moves: list[MoveAnalysis]
    our_pieces: list[PieceStatus]
    threats_to_us: list[str]  # "Queen attacks Knight on f3"
    threats_to_them: list[str]
    evaluation: float  # in pawns (positive = good for side to move)
    evaluation_text: str  # "White has slight advantage"
    game_phase: str  # "opening", "middlegame", "endgame"


class EngineAnalyzer:
    """
    Stockfish chess engine analyzer.

    Provides position analysis including:
    - Top N candidate moves with evaluations
    - Piece threat detection (attacked, defended, hanging)
    - Tactical information
    - Game phase detection
    """

    # Common Stockfish binary locations
    STOCKFISH_PATHS = [
        "stockfish",  # In PATH
        "/usr/local/bin/stockfish",  # Homebrew (Intel Mac)
        "/opt/homebrew/bin/stockfish",  # Homebrew (Apple Silicon)
        "/usr/bin/stockfish",  # Linux package manager
        "/usr/games/stockfish",  # Debian/Ubuntu
    ]

    def __init__(
        self,
        stockfish_path: str | None = None,
        depth: int = 20,
        time_limit_ms: int = 5000,
    ):
        """
        Initialize the engine analyzer.

        Args:
            stockfish_path: Path to Stockfish binary (auto-detected if None)
            depth: Search depth for analysis
            time_limit_ms: Time limit in milliseconds
        """
        self._stockfish_path = stockfish_path or self._find_stockfish()
        self._depth = depth
        self._time_limit_ms = time_limit_ms
        self._engine: chess.engine.UciProtocol | None = None
        self._transport: asyncio.SubprocessTransport | None = None
        self._initialized = False

    @classmethod
    def _find_stockfish(cls) -> str | None:
        """Auto-detect Stockfish binary location."""
        for path in cls.STOCKFISH_PATHS:
            if shutil.which(path):
                return path
        return None

    @property
    def is_available(self) -> bool:
        """Check if Stockfish is available (binary exists)."""
        return self._stockfish_path is not None

    async def initialize(self) -> bool:
        """
        Initialize the engine connection.

        Returns:
            True if initialization succeeded, False otherwise.
        """
        if self._initialized:
            return True

        if not self.is_available:
            return False

        try:
            self._transport, self._engine = await chess.engine.popen_uci(
                self._stockfish_path
            )
            self._initialized = True
            return True
        except Exception as e:
            print(f"[EngineAnalyzer] Failed to initialize Stockfish: {e}")
            return False

    async def close(self) -> None:
        """Close the engine connection."""
        if self._engine:
            try:
                await self._engine.quit()
            except Exception:
                pass  # Engine may already be dead
            self._engine = None
            self._transport = None
            self._initialized = False

    def _reset(self) -> None:
        """Reset engine state so it will be re-initialized on next use."""
        self._engine = None
        self._transport = None
        self._initialized = False

    async def analyze_position(
        self, board: "ChessBoard", num_moves: int = 3
    ) -> PositionAnalysis | None:
        """
        Analyze a chess position.

        Args:
            board: The chess board to analyze
            num_moves: Number of top moves to return

        Returns:
            PositionAnalysis or None if engine is unavailable
        """
        if not await self.initialize():
            return None

        chess_board = board._board

        # Run analysis with multipv to get top N moves
        limit = chess.engine.Limit(
            depth=self._depth,
            time=self._time_limit_ms / 1000.0,
        )

        try:
            analysis_results = await self._engine.analyse(
                chess_board, limit, multipv=num_moves
            )
        except Exception as e:
            print(f"[EngineAnalyzer] Analysis failed: {e}")
            print("[EngineAnalyzer] Resetting engine — will relaunch on next request")
            self._reset()
            return None

        # Parse engine results into MoveAnalysis objects
        top_moves = self._parse_analysis_results(analysis_results, chess_board)

        # Analyze piece status (attacks, defenses, hanging pieces)
        our_pieces, threats_to_us, threats_to_them = self._analyze_piece_status(
            chess_board
        )

        # Get overall evaluation from best move
        evaluation = 0.0
        if top_moves and top_moves[0].centipawn_score is not None:
            evaluation = top_moves[0].centipawn_score / 100.0
        elif top_moves and top_moves[0].mate_in is not None:
            # Large value for mate
            mate_in = top_moves[0].mate_in
            evaluation = 100.0 if mate_in > 0 else -100.0

        evaluation_text = self._evaluation_to_text(evaluation, top_moves)
        game_phase = self._detect_game_phase(chess_board)

        return PositionAnalysis(
            top_moves=top_moves,
            our_pieces=our_pieces,
            threats_to_us=threats_to_us,
            threats_to_them=threats_to_them,
            evaluation=evaluation,
            evaluation_text=evaluation_text,
            game_phase=game_phase,
        )

    def _parse_analysis_results(
        self, results: list[chess.engine.InfoDict], board: chess.Board
    ) -> list[MoveAnalysis]:
        """Parse engine analysis results into MoveAnalysis objects."""
        moves = []

        for info in results:
            if "pv" not in info or not info["pv"]:
                continue

            move = info["pv"][0]

            # Get score
            centipawn_score = None
            mate_in = None
            if "score" in info:
                score = info["score"].relative
                if score.is_mate():
                    mate_in = score.mate()
                else:
                    centipawn_score = score.score()

            # Get move details
            uci = move.uci()
            san = board.san(move)

            # Check if capture
            is_capture = board.is_capture(move)
            captured_piece = None
            if is_capture:
                captured = board.piece_at(move.to_square)
                if captured:
                    captured_piece = chess.piece_name(captured.piece_type)

            # Check if check
            board.push(move)
            is_check = board.is_check()
            board.pop()

            moves.append(
                MoveAnalysis(
                    uci=uci,
                    san=san,
                    centipawn_score=centipawn_score,
                    mate_in=mate_in,
                    is_capture=is_capture,
                    is_check=is_check,
                    captured_piece=captured_piece,
                )
            )

        return moves

    def _analyze_piece_status(
        self, board: chess.Board
    ) -> tuple[list[PieceStatus], list[str], list[str]]:
        """
        Analyze all pieces for attack/defense status.

        Returns:
            (our_pieces, threats_to_us, threats_to_them)
        """
        our_color = board.turn
        their_color = not our_color

        our_pieces = []
        threats_to_us = []
        threats_to_them = []

        piece_names = {
            chess.PAWN: "pawn",
            chess.KNIGHT: "knight",
            chess.BISHOP: "bishop",
            chess.ROOK: "rook",
            chess.QUEEN: "queen",
            chess.KING: "king",
        }

        # Analyze our pieces
        for square in chess.SQUARES:
            piece = board.piece_at(square)
            if piece is None or piece.color != our_color:
                continue

            square_name = chess.square_name(square)
            piece_type = piece_names[piece.piece_type]

            # Find attackers (their pieces attacking this square)
            attackers = list(board.attackers(their_color, square))
            attacker_names = []
            for att_sq in attackers:
                att_piece = board.piece_at(att_sq)
                if att_piece:
                    att_name = piece_names[att_piece.piece_type]
                    attacker_names.append(f"{att_name}_{chess.square_name(att_sq)}")

            # Find defenders (our pieces defending this square)
            defenders = list(board.attackers(our_color, square))
            defender_names = []
            for def_sq in defenders:
                if def_sq == square:
                    continue  # Skip the piece itself
                def_piece = board.piece_at(def_sq)
                if def_piece:
                    def_name = piece_names[def_piece.piece_type]
                    defender_names.append(f"{def_name}_{chess.square_name(def_sq)}")

            is_attacked = len(attacker_names) > 0
            is_defended = len(defender_names) > 0
            is_hanging = is_attacked and not is_defended

            status = PieceStatus(
                piece_type=piece_type,
                square=square_name,
                is_attacked=is_attacked,
                is_defended=is_defended,
                is_hanging=is_hanging,
                attackers=attacker_names,
                defenders=defender_names,
            )
            our_pieces.append(status)

            # Generate threat descriptions
            if is_hanging:
                for att in attacker_names:
                    att_type, att_sq = att.rsplit("_", 1)
                    threats_to_us.append(
                        f"{att_type.capitalize()} on {att_sq} attacks "
                        f"undefended {piece_type.capitalize()} on {square_name}"
                    )
            elif is_attacked:
                for att in attacker_names:
                    att_type, att_sq = att.rsplit("_", 1)
                    threats_to_us.append(
                        f"{att_type.capitalize()} on {att_sq} attacks "
                        f"{piece_type.capitalize()} on {square_name}"
                    )

        # Analyze their pieces for threats we pose
        for square in chess.SQUARES:
            piece = board.piece_at(square)
            if piece is None or piece.color != their_color:
                continue

            square_name = chess.square_name(square)
            piece_type = piece_names[piece.piece_type]

            # Find our attackers
            our_attackers = list(board.attackers(our_color, square))

            # Find their defenders
            their_defenders = list(board.attackers(their_color, square))
            # Exclude the piece itself
            their_defenders = [sq for sq in their_defenders if sq != square]

            if our_attackers and not their_defenders:
                # Their piece is hanging
                for att_sq in our_attackers:
                    att_piece = board.piece_at(att_sq)
                    if att_piece:
                        att_name = piece_names[att_piece.piece_type]
                        threats_to_them.append(
                            f"Our {att_name.capitalize()} on {chess.square_name(att_sq)} "
                            f"attacks their undefended {piece_type.capitalize()} on {square_name}"
                        )

        return our_pieces, threats_to_us, threats_to_them

    def _evaluation_to_text(
        self, evaluation: float, top_moves: list[MoveAnalysis]
    ) -> str:
        """Convert numeric evaluation to human-readable text."""
        # Check for mate
        if top_moves and top_moves[0].mate_in is not None:
            mate_in = top_moves[0].mate_in
            if mate_in > 0:
                return f"Mate in {mate_in} moves"
            else:
                return f"Getting mated in {abs(mate_in)} moves"

        # Convert centipawn to description
        if evaluation > 3.0:
            return "Winning position"
        elif evaluation > 1.5:
            return "Clear advantage"
        elif evaluation > 0.5:
            return "Slight advantage"
        elif evaluation > -0.5:
            return "Equal position"
        elif evaluation > -1.5:
            return "Slight disadvantage"
        elif evaluation > -3.0:
            return "Clear disadvantage"
        else:
            return "Losing position"

    def _detect_game_phase(self, board: chess.Board) -> str:
        """Detect the current game phase based on material and development."""
        # Count material
        queens = len(board.pieces(chess.QUEEN, chess.WHITE)) + len(
            board.pieces(chess.QUEEN, chess.BLACK)
        )
        rooks = len(board.pieces(chess.ROOK, chess.WHITE)) + len(
            board.pieces(chess.ROOK, chess.BLACK)
        )
        minor_pieces = (
            len(board.pieces(chess.BISHOP, chess.WHITE))
            + len(board.pieces(chess.BISHOP, chess.BLACK))
            + len(board.pieces(chess.KNIGHT, chess.WHITE))
            + len(board.pieces(chess.KNIGHT, chess.BLACK))
        )

        total_pieces = queens * 9 + rooks * 5 + minor_pieces * 3

        # Simple heuristic for game phase
        if board.fullmove_number <= 10:
            return "opening"
        elif total_pieces <= 12:
            return "endgame"
        else:
            return "middlegame"

    async def __aenter__(self) -> "EngineAnalyzer":
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()
