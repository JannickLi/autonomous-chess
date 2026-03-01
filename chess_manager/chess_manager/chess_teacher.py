import asyncio
import os

import chess
import chess.engine
from mistralai import Mistral

from chess_manager.voice.chess_tts import CHESS_VOICES, ChessTTS
from dotenv import load_dotenv

_SYSTEM_PROMPT = """\
You are a witty, charismatic chess commentator with the energy of a sports broadcaster \
calling an epic battle. You will receive facts about a chess move including Stockfish evaluations.
If the move is legal, describe what it achieves using vivid metaphors and dramatic flair — \
like pieces are warriors on a battlefield.
If the move is illegal, roast the move with humor while explaining why it's not allowed.
Keep it to 2-3 punchy sentences MAX. No raw notation. Make it fun to listen to.\
"""

_ANALYSIS_DEPTH = 18

STOCKFISH_PATH = "/usr/games/stockfish"

def _format_score(score: chess.engine.PovScore) -> str:
    white = score.white()
    if white.is_mate():
        m = white.mate()
        return f"Mate in {m}" if m > 0 else f"Black mates in {abs(m)}"
    cp = white.score()
    if cp == 0:
        return "equal (0.00)"
    side = "White" if cp > 0 else "Black"
    return f"{cp / 100:+.2f} ({side} is better)"


def _illegality_reason(board: chess.Board, move: chess.Move) -> str:
    """Return a human-readable explanation of why a move is illegal."""
    piece = board.piece_at(move.from_square)
    from_name = chess.square_name(move.from_square)
    to_name = chess.square_name(move.to_square)
    turn = "White" if board.turn == chess.WHITE else "Black"

    if piece is None:
        return f"There is no piece on {from_name}."
    if piece.color != board.turn:
        other = "White" if piece.color == chess.WHITE else "Black"
        return f"It is {turn}'s turn, but the piece on {from_name} belongs to {other}."
    if not board.is_pseudo_legal(move):
        return (
            f"A {chess.piece_name(piece.piece_type)} cannot move from {from_name} to {to_name} "
            f"— that is not a valid movement pattern for this piece."
        )
    # Pseudo-legal but not legal → must expose king
    return f"This move would leave {turn}'s king in check, which is not allowed."


class ChessTeacher:
    """
    Analyzes a chess move with Stockfish, then generates a spoken teaching explanation.

    Usage:
        async with ChessTeacher(...) as teacher:
            await teacher.teach(fen=chess.STARTING_FEN, move="e2e4")
            await teacher.teach(fen=chess.STARTING_FEN, move="e2e5", validate_legal=False)
    """

    def __init__(
        self,
        model_id: str = "mistral-large-latest",
        voice_id: str = CHESS_VOICES["bishop"],
        analysis_depth: int = _ANALYSIS_DEPTH,
        tts: ChessTTS | None = None,
    ):
        load_dotenv()
        mistral_api_key = os.getenv("MISTRAL_API_KEY")
        elevenlabs_api_key = os.getenv("ELEVENLABS_API_KEY")

        self._mistral = Mistral(api_key=mistral_api_key)
        self._tts = tts or ChessTTS(api_key=elevenlabs_api_key)
        self._model_id = model_id
        self._voice_id = voice_id
        self._depth = analysis_depth
        self._engine: chess.engine.UciProtocol | None = None

    async def _get_engine(self) -> chess.engine.UciProtocol:
        if self._engine is None:
            _, self._engine = await chess.engine.popen_uci(STOCKFISH_PATH)
        return self._engine

    async def close(self):
        if self._engine is not None:
            await self._engine.quit()
            self._engine = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self.close()

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

    async def _stockfish_eval(self, board: chess.Board) -> chess.engine.PovScore:
        engine = await self._get_engine()
        info = await engine.analyse(board, chess.engine.Limit(depth=self._depth))
        return info["score"]

    async def _analyze(self, board: chess.Board, move: chess.Move) -> dict:
        piece = board.piece_at(move.from_square)
        captured = board.piece_at(move.to_square)
        is_legal = move in board.legal_moves

        # SAN requires a legal move; fall back to UCI for illegal ones
        try:
            san = board.san(move) if is_legal else move.uci()
        except Exception:
            san = move.uci()

        score_before = await self._stockfish_eval(board)

        base = {
            "is_legal": is_legal,
            "move_number": board.fullmove_number,
            "color": "White" if board.turn == chess.WHITE else "Black",
            "san": san,
            "piece": chess.piece_name(piece.piece_type) if piece else "none",
            "from_square": chess.square_name(move.from_square),
            "to_square": chess.square_name(move.to_square),
            "captures": chess.piece_name(captured.piece_type) if captured else None,
            "eval_before": _format_score(score_before),
            "board_before": str(board),
        }

        if not is_legal:
            base["illegality_reason"] = _illegality_reason(board, move)
            return base

        board_after = board.copy()
        board_after.push(move)
        score_after = await self._stockfish_eval(board_after)

        base.update(
            {
                "is_castling": board.is_castling(move),
                "is_en_passant": board.is_en_passant(move),
                "is_promotion": move.promotion is not None,
                "promotion_piece": (
                    chess.piece_name(move.promotion) if move.promotion else None
                ),
                "gives_check": board_after.is_check(),
                "is_checkmate": board_after.is_checkmate(),
                "is_stalemate": board_after.is_stalemate(),
                "eval_after": _format_score(score_after),
                "fen_after": board_after.fen(),
                "board_before_unicode": board.unicode(),
                "board_after_unicode": board_after.unicode(),
            }
        )
        return base

    def _build_facts(self, a: dict) -> str:
        lines = [
            f"Move {a['move_number']}: {a['color']} attempts to move the {a['piece']} "
            f"from {a['from_square']} to {a['to_square']}.",
        ]

        if not a["is_legal"]:
            lines.append(f"This move is ILLEGAL. Reason: {a['illegality_reason']}")
            lines.append(
                f"\nStockfish evaluation of the current position: {a['eval_before']}"
            )
            lines.append(f"\nBoard:\n{a['board_before']}")
            return "\n".join(lines)

        if a.get("captures"):
            lines.append(f"It captures the opponent's {a['captures']}.")
        if a.get("is_castling"):
            lines.append("This is a castling move.")
        if a.get("is_en_passant"):
            lines.append("This is an en passant capture.")
        if a.get("is_promotion"):
            lines.append(f"The pawn promotes to a {a['promotion_piece']}.")
        if a.get("is_checkmate"):
            lines.append("This move delivers checkmate.")
        elif a.get("gives_check"):
            lines.append("This move puts the opponent in check.")
        if a.get("is_stalemate"):
            lines.append("This move results in stalemate — a draw.")
        lines.append(f"\nStockfish evaluation before: {a['eval_before']}")
        lines.append(f"Stockfish evaluation after:  {a['eval_after']}")
        lines.append(f"\nBoard before the move:\n{a['board_before_unicode']}")
        lines.append(f"\nBoard after the move:\n{a['board_after_unicode']}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse_move(
        self, board: chess.Board, move: str, validate_legal: bool = True
    ) -> chess.Move:
        """
        Parse UCI (e2e4) or SAN (e4, Nf3) notation.
        If validate_legal=False, illegal moves are accepted (UCI only for illegal ones).
        """
        try:
            m = chess.Move.from_uci(move)
            if not validate_legal or m in board.legal_moves:
                return m
        except ValueError:
            pass
        return board.parse_san(move)  # parse_san always validates legality

    async def teach(self, fen: str, move: str, validate_legal: bool = True) -> str:
        """
        Analyze a move, generate teaching commentary, and speak it.

        Args:
            fen:            FEN of the position BEFORE the move.
            move:           Move in UCI or SAN notation.
            validate_legal: If True (default), raises ValueError for illegal moves.
                            If False, explains why the move is not allowed instead.
        """
        board = chess.Board(fen)
        parsed = self.parse_move(board, move, validate_legal=validate_legal)
        analysis = await self._analyze(board, parsed)
        
        facts = self._build_facts(analysis)

        print(f"\n[Position facts]\n{facts}\n")

        response = await asyncio.to_thread(
            self._mistral.chat.complete,
            model=self._model_id,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": facts},
            ],
        )
        commentary = response.choices[0].message.content.strip()

        print(f"[Teacher]\n{commentary}\n")
        await self._tts.speak(commentary, self._voice_id)
        return commentary


# ------------------------------------------------------------------
# Demo
# ------------------------------------------------------------------


async def main():
    async with ChessTeacher(
    ) as teacher:

        # Legal move
        # await teacher.teach(fen=chess.STARTING_FEN, move="e2e4")

        # Illegal move — pawn can't jump 3 squares
        await teacher.teach(fen=chess.STARTING_FEN, move="e2e5", validate_legal=False)


if __name__ == "__main__":
    asyncio.run(main())
