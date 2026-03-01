"""Move generation API routes (external API)."""

from fastapi import APIRouter, HTTPException

from backend.orchestration import get_orchestrator
from backend.chess_engine import MoveValidator
from backend.api.schemas import (
    GenerateMoveRequest,
    GenerateMoveResponse,
    ProposalResponse,
    DeliberationResponse,
)

router = APIRouter(prefix="/api/move", tags=["moves"])


@router.post("/generate", response_model=GenerateMoveResponse)
async def generate_move(request: GenerateMoveRequest):
    """
    Generate a move for a given position.

    This is the main external API endpoint for move generation.
    It does not require an active game session.
    """
    # Validate FEN
    valid, error = MoveValidator.validate_fen(request.fen)
    if not valid:
        raise HTTPException(status_code=400, detail=error)

    orchestrator = get_orchestrator()

    try:
        result = await orchestrator.generate_move_for_position(
            request.fen, request.strategy
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Build response
    proposals = [
        ProposalResponse(
            agent_id=p.agent_id,
            description=p.description or p.move,
            reasoning=p.reasoning,
            piece_type=p.piece_type,
            piece_square=p.piece_square,
            piece_impacts=p.piece_impacts,
        )
        for p in result.proposals
    ]

    votes = None
    if result.votes:
        votes = [
            {
                "agent_id": v.agent_id,
                "voted_for": v.voted_for,
                "reasoning": v.reasoning,
            }
            for v in result.votes
        ]

    return GenerateMoveResponse(
        move=result.selected_move,
        reasoning=result.reasoning,
        deliberation=DeliberationResponse(
            proposals=proposals,
            votes=votes,
            summary=result.deliberation_summary,
        ),
    )


@router.post("/validate")
async def validate_move(fen: str, move: str):
    """Validate if a move is legal for a position."""
    from backend.chess_engine import ChessBoard

    valid, error = MoveValidator.validate_fen(fen)
    if not valid:
        raise HTTPException(status_code=400, detail=error)

    board = ChessBoard.from_fen(fen)
    valid, error = MoveValidator.validate_move(board, move)

    return {
        "valid": valid,
        "error": error,
        "move": move,
        "fen": fen,
    }


@router.get("/legal")
async def get_legal_moves(fen: str):
    """Get all legal moves for a position."""
    from backend.chess_engine import ChessBoard

    valid, error = MoveValidator.validate_fen(fen)
    if not valid:
        raise HTTPException(status_code=400, detail=error)

    board = ChessBoard.from_fen(fen)
    moves = board.get_legal_moves()

    return {
        "fen": fen,
        "turn": board.turn_name,
        "moves": [
            {
                "uci": m.uci,
                "san": m.san,
                "from": m.from_square,
                "to": m.to_square,
                "piece": m.piece,
                "is_capture": m.is_capture,
            }
            for m in moves
        ],
        "count": len(moves),
    }


@router.get("/suggestions")
async def get_move_suggestions(fen: str, partial: str = ""):
    """Get move suggestions/autocomplete for a partial move."""
    from backend.chess_engine import ChessBoard

    valid, error = MoveValidator.validate_fen(fen)
    if not valid:
        raise HTTPException(status_code=400, detail=error)

    board = ChessBoard.from_fen(fen)
    suggestions = MoveValidator.get_move_suggestions(board, partial)

    return {
        "fen": fen,
        "partial": partial,
        "suggestions": suggestions,
    }
