"""Move validation utilities."""

import chess

from .board import ChessBoard


class MoveValidator:
    """Validates chess moves and provides error messages."""

    @staticmethod
    def validate_move(board: ChessBoard, move: str) -> tuple[bool, str | None]:
        """
        Validate a move on the given board.

        Returns:
            Tuple of (is_valid, error_message)
            If valid, error_message is None
        """
        if not move or not move.strip():
            return False, "Move cannot be empty"

        move = move.strip()

        # Try parsing as UCI first, then SAN
        try:
            chess_move = board._board.parse_uci(move)
        except chess.InvalidMoveError:
            try:
                chess_move = board._board.parse_san(move)
            except chess.InvalidMoveError:
                return False, f"Invalid move notation: '{move}'"
            except chess.AmbiguousMoveError:
                return False, f"Ambiguous move: '{move}' - please specify which piece"

        # Check if move is legal
        if chess_move not in board._board.legal_moves:
            # Provide more specific error
            piece = board._board.piece_at(chess_move.from_square)
            if piece is None:
                return False, f"No piece at {chess.square_name(chess_move.from_square)}"

            if piece.color != board._board.turn:
                return False, "Cannot move opponent's piece"

            # Check if move would leave king in check
            board._board.push(chess_move)
            was_in_check = board._board.was_into_check()
            board._board.pop()

            if was_in_check:
                return False, "Move would leave king in check"

            return False, f"Illegal move: {move}"

        return True, None

    @staticmethod
    def validate_fen(fen: str) -> tuple[bool, str | None]:
        """
        Validate a FEN string.

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            board = chess.Board(fen)
            if not board.is_valid():
                return False, "Invalid board position"
            return True, None
        except ValueError as e:
            return False, f"Invalid FEN: {e}"

    @staticmethod
    def get_move_suggestions(board: ChessBoard, partial_move: str) -> list[str]:
        """
        Get move suggestions that match a partial move string.

        Useful for move completion/autocomplete.
        """
        partial = partial_move.lower().strip()
        suggestions = []

        for move in board._board.legal_moves:
            uci = move.uci()
            san = board._board.san(move)

            if uci.startswith(partial) or san.lower().startswith(partial):
                suggestions.append(uci)

        return suggestions[:10]  # Limit to 10 suggestions
