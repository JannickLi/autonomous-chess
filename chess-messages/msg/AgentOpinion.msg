# Individual agent opinion from deliberation
# Each chess piece agent proposes a move with reasoning

string piece_type        # e.g., "knight", "queen", "pawn"
string piece_color       # "white" or "black"
string proposed_move     # UCI notation (e.g., "e2e4")
string reasoning         # LLM-generated explanation
float32 confidence       # 0.0-1.0
int32 vote_weight        # Based on piece value (pawn=1, knight/bishop=3, rook=5, queen=9, king=0)
