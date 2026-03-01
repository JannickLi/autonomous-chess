# Command to execute a chess move
# Published by agent node, subscribed by robot control

std_msgs/Header header

# UCI notation move (e.g., "e2e4", "e1g1" for castling)
string move_uci

# Source square (e.g., "e2")
string from_square

# Destination square (e.g., "e4")
string to_square

# Piece type: "pawn", "knight", "bishop", "rook", "queen", "king"
string piece_type

# Piece color: "white" or "black"
string piece_color

# Move flags
bool is_capture
bool is_castling
bool is_en_passant
bool is_promotion

# Promotion piece type if is_promotion=true
# "queen", "rook", "bishop", or "knight"
string promotion_piece

# Captured piece type if is_capture=true (for cleanup)
string captured_piece

# Castling type if is_castling=true: "kingside" or "queenside"
string castling_type

# Current board FEN (for context/validation)
string board_fen
