"""Chess board state wrapper using python-chess."""

from dataclasses import dataclass, field
from typing import Iterator

import chess


@dataclass
class PieceInfo:
    """Information about a piece on the board."""

    piece_type: chess.PieceType
    color: chess.Color
    square: chess.Square
    symbol: str
    name: str

    @property
    def square_name(self) -> str:
        """Get algebraic notation of square (e.g., 'e4')."""
        return chess.square_name(self.square)

    @property
    def color_name(self) -> str:
        """Get color name ('white' or 'black')."""
        return "white" if self.color == chess.WHITE else "black"


@dataclass
class MoveInfo:
    """Information about a move."""

    uci: str
    san: str
    from_square: str
    to_square: str
    piece: str
    is_capture: bool
    is_check: bool
    is_checkmate: bool
    promotion: str | None = None


@dataclass
class ChessBoard:
    """Wrapper around python-chess Board with additional utilities."""

    _board: chess.Board = field(default_factory=chess.Board)

    @classmethod
    def from_fen(cls, fen: str) -> "ChessBoard":
        """Create a board from FEN notation."""
        board = cls()
        board._board.set_fen(fen)
        return board

    @property
    def fen(self) -> str:
        """Get current FEN notation."""
        return self._board.fen()

    @property
    def turn(self) -> chess.Color:
        """Get whose turn it is."""
        return self._board.turn

    @property
    def turn_name(self) -> str:
        """Get turn as string ('white' or 'black')."""
        return "white" if self._board.turn == chess.WHITE else "black"

    @property
    def fullmove_number(self) -> int:
        """Get the full move number."""
        return self._board.fullmove_number

    @property
    def is_game_over(self) -> bool:
        """Check if the game is over."""
        return self._board.is_game_over()

    @property
    def is_check(self) -> bool:
        """Check if current player is in check."""
        return self._board.is_check()

    @property
    def is_checkmate(self) -> bool:
        """Check if current player is in checkmate."""
        return self._board.is_checkmate()

    @property
    def is_stalemate(self) -> bool:
        """Check if the game is a stalemate."""
        return self._board.is_stalemate()

    def get_result(self) -> str | None:
        """Get game result if game is over."""
        if not self.is_game_over:
            return None
        result = self._board.result()
        return result

    def get_legal_moves(self) -> list[MoveInfo]:
        """Get all legal moves for current player."""
        moves = []
        for move in self._board.legal_moves:
            moves.append(self._move_to_info(move))
        return moves

    def get_legal_moves_uci(self) -> list[str]:
        """Get all legal moves in UCI notation."""
        return [move.uci() for move in self._board.legal_moves]

    def get_legal_moves_for_piece(self, square: chess.Square) -> list[MoveInfo]:
        """Get legal moves for a specific piece."""
        moves = []
        for move in self._board.legal_moves:
            if move.from_square == square:
                moves.append(self._move_to_info(move))
        return moves

    def get_pieces(self, color: chess.Color | None = None) -> list[PieceInfo]:
        """Get all pieces, optionally filtered by color."""
        pieces = []
        for square in chess.SQUARES:
            piece = self._board.piece_at(square)
            if piece is not None:
                if color is None or piece.color == color:
                    pieces.append(self._piece_to_info(piece, square))
        return pieces

    def get_movable_pieces(self) -> list[PieceInfo]:
        """Get all pieces that have at least one legal move."""
        movable_squares = set()
        for move in self._board.legal_moves:
            movable_squares.add(move.from_square)

        pieces = []
        for square in movable_squares:
            piece = self._board.piece_at(square)
            if piece is not None:
                pieces.append(self._piece_to_info(piece, square))
        return pieces

    def get_piece_at(self, square: str | chess.Square) -> PieceInfo | None:
        """Get piece at a given square."""
        if isinstance(square, str):
            square = chess.parse_square(square)
        piece = self._board.piece_at(square)
        if piece is None:
            return None
        return self._piece_to_info(piece, square)

    def make_move(self, move: str) -> MoveInfo:
        """Make a move in UCI or SAN notation. Returns move info."""
        try:
            chess_move = self._board.parse_uci(move)
        except chess.InvalidMoveError:
            chess_move = self._board.parse_san(move)

        move_info = self._move_to_info(chess_move)
        self._board.push(chess_move)
        return move_info

    def is_legal_move(self, move: str) -> bool:
        """Check if a move is legal."""
        try:
            chess_move = self._board.parse_uci(move)
            return chess_move in self._board.legal_moves
        except chess.InvalidMoveError:
            try:
                chess_move = self._board.parse_san(move)
                return chess_move in self._board.legal_moves
            except chess.InvalidMoveError:
                return False

    def copy(self) -> "ChessBoard":
        """Create a copy of the board."""
        new_board = ChessBoard()
        new_board._board = self._board.copy()
        return new_board

    def get_board_visual(self) -> str:
        """Get ASCII representation of the board."""
        return str(self._board)

    def get_move_history(self) -> list[str]:
        """Get list of moves made in SAN notation."""
        moves = []
        board_copy = self._board.copy()
        while board_copy.move_stack:
            board_copy.pop()

        for move in self._board.move_stack:
            san = board_copy.san(move)
            moves.append(san)
            board_copy.push(move)
        return moves

    def _piece_to_info(self, piece: chess.Piece, square: chess.Square) -> PieceInfo:
        """Convert chess.Piece to PieceInfo."""
        piece_names = {
            chess.PAWN: "pawn",
            chess.KNIGHT: "knight",
            chess.BISHOP: "bishop",
            chess.ROOK: "rook",
            chess.QUEEN: "queen",
            chess.KING: "king",
        }
        return PieceInfo(
            piece_type=piece.piece_type,
            color=piece.color,
            square=square,
            symbol=piece.symbol(),
            name=piece_names[piece.piece_type],
        )

    def _move_to_info(self, move: chess.Move) -> MoveInfo:
        """Convert chess.Move to MoveInfo."""
        piece = self._board.piece_at(move.from_square)
        piece_symbol = piece.symbol() if piece else "?"

        # Check if it's a capture
        is_capture = self._board.is_capture(move)

        # Temporarily make the move to check for check/checkmate
        san = self._board.san(move)
        self._board.push(move)
        is_check = self._board.is_check()
        is_checkmate = self._board.is_checkmate()
        self._board.pop()

        promotion = None
        if move.promotion:
            promotion = chess.piece_symbol(move.promotion)

        return MoveInfo(
            uci=move.uci(),
            san=san,
            from_square=chess.square_name(move.from_square),
            to_square=chess.square_name(move.to_square),
            piece=piece_symbol,
            is_capture=is_capture,
            is_check=is_check,
            is_checkmate=is_checkmate,
            promotion=promotion,
        )

    def __iter__(self) -> Iterator[PieceInfo]:
        """Iterate over all pieces on the board."""
        return iter(self.get_pieces())
