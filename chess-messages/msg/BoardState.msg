# Board state from chess piece detection
# Published by perception node after capturing and processing camera image

std_msgs/Header header

# Detection success flag
bool success

# FEN notation of detected position
# e.g., "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"
string fen

# Square names in order (a1, a2, ..., h8)
string[64] squares

# Piece at each square ("" if empty, uppercase for white, lowercase for black)
# P=pawn, R=rook, N=knight, B=bishop, Q=queen, K=king
string[64] pieces

# Average detection confidence (0.0 to 1.0)
float32 confidence

# Error message if success=false
string error
