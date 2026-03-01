"""Game management API routes."""

from fastapi import APIRouter, HTTPException

from backend.orchestration import get_orchestrator
from backend.api.schemas import (
    CreateGameRequest,
    CreateGameResponse,
    GameResponse,
    MakeMoveRequest,
    MakeMoveResponse,
    MoveHistoryResponse,
)

router = APIRouter(prefix="/api/games", tags=["games"])


@router.post("", response_model=CreateGameResponse)
async def create_game(request: CreateGameRequest):
    """Create a new chess game."""
    orchestrator = get_orchestrator()
    session = orchestrator.create_session(
        fen=request.fen,
        strategy=request.strategy,
        white_player=request.white_player,
        black_player=request.black_player,
    )
    return CreateGameResponse(
        id=session.id,
        fen=session.board.fen,
        state=session.state.value,
        strategy=session.strategy,
        current_turn=session.current_turn,
        white_player=session.white_player,
        black_player=session.black_player,
    )


@router.get("", response_model=list[GameResponse])
async def list_games():
    """List all active games."""
    orchestrator = get_orchestrator()
    sessions = orchestrator.list_sessions()
    return [GameResponse(**s.to_dict()) for s in sessions]


@router.get("/{game_id}", response_model=GameResponse)
async def get_game(game_id: str):
    """Get game state by ID."""
    orchestrator = get_orchestrator()
    session = orchestrator.get_session(game_id)
    if not session:
        raise HTTPException(status_code=404, detail="Game not found")
    return GameResponse(**session.to_dict())


@router.delete("/{game_id}")
async def delete_game(game_id: str):
    """Delete a game."""
    orchestrator = get_orchestrator()
    if not orchestrator.delete_session(game_id):
        raise HTTPException(status_code=404, detail="Game not found")
    return {"status": "deleted", "id": game_id}


@router.post("/{game_id}/move", response_model=MakeMoveResponse)
async def make_move(game_id: str, request: MakeMoveRequest):
    """Make a player move."""
    orchestrator = get_orchestrator()

    try:
        session, move_info = await orchestrator.make_player_move(game_id, request.move)
        return MakeMoveResponse(**move_info)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{game_id}/agent-move")
async def generate_agent_move(game_id: str):
    """Generate and execute an agent move."""
    orchestrator = get_orchestrator()

    try:
        session, result = await orchestrator.generate_agent_move(game_id)
        return {
            "move": result.selected_move,
            "reasoning": result.reasoning,
            "fen": session.board.fen,
            "is_check": session.board.is_check,
            "is_checkmate": session.board.is_checkmate,
            "is_game_over": session.is_game_over,
            "result": session.result,
            "deliberation": {
                "proposals": [
                    {
                        "agent_id": p.agent_id,
                        "description": p.description or p.move,
                        "reasoning": p.reasoning,
                        "piece_impacts": p.piece_impacts,
                    }
                    for p in result.proposals
                ],
                "votes": [
                    {
                        "agent_id": v.agent_id,
                        "voted_for": v.voted_for,
                        "reasoning": v.reasoning,
                    }
                    for v in result.votes
                ],
                "summary": result.deliberation_summary,
            },
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{game_id}/history", response_model=MoveHistoryResponse)
async def get_move_history(game_id: str):
    """Get move history for a game."""
    orchestrator = get_orchestrator()
    session = orchestrator.get_session(game_id)
    if not session:
        raise HTTPException(status_code=404, detail="Game not found")

    history = session.get_move_history()
    return MoveHistoryResponse(
        game_id=game_id,
        moves=history,
        total_moves=len(history),
    )


@router.get("/{game_id}/board")
async def get_board_visual(game_id: str):
    """Get ASCII representation of the board."""
    orchestrator = get_orchestrator()
    session = orchestrator.get_session(game_id)
    if not session:
        raise HTTPException(status_code=404, detail="Game not found")

    return {
        "fen": session.board.fen,
        "board": session.board.get_board_visual(),
        "turn": session.current_turn,
    }


@router.put("/{game_id}/strategy")
async def update_strategy(game_id: str, strategy: str):
    """Update the strategy for an active game."""
    orchestrator = get_orchestrator()
    session = orchestrator.get_session(game_id)
    if not session:
        raise HTTPException(status_code=404, detail="Game not found")

    # Validate strategy exists
    available = orchestrator.list_strategies()
    if strategy not in available:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown strategy: {strategy}. Available: {available}"
        )

    session.strategy = strategy
    return {
        "status": "updated",
        "game_id": game_id,
        "strategy": strategy,
    }


# Personality Management

@router.get("/config/personalities")
async def list_personalities():
    """List available personality presets."""
    orchestrator = get_orchestrator()
    return {
        "current": orchestrator.get_personality_preset(),
        "available": orchestrator.list_personality_presets(),
    }


@router.put("/config/personality")
async def set_personality(preset: str):
    """Set the personality preset for all agents."""
    orchestrator = get_orchestrator()
    try:
        orchestrator.set_personality_preset(preset)
        return {
            "status": "updated",
            "personality": preset,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/config/personalities/details")
async def get_personality_details():
    """Get detailed personality values for all pieces."""
    orchestrator = get_orchestrator()
    from backend.agents.personality import PIECE_PERSONALITIES, get_personality_for_piece

    overrides = orchestrator.get_personality_overrides()
    result = {}

    for piece_type in ["pawn", "knight", "bishop", "rook", "queen", "king"]:
        personality = get_personality_for_piece(piece_type, overrides.get(piece_type))
        result[piece_type] = {
            "self_preservation": personality.self_preservation,
            "personal_glory": personality.personal_glory,
            "team_victory": personality.team_victory,
            "aggression": personality.aggression,
            "positional_dominance": personality.positional_dominance,
            "cooperation": personality.cooperation,
        }

    return {
        "preset": orchestrator.get_personality_preset(),
        "pieces": result,
    }


@router.put("/config/personalities/{piece_type}")
async def update_piece_personality(piece_type: str, weights: dict):
    """Update personality weights for a specific piece type."""
    orchestrator = get_orchestrator()
    try:
        orchestrator.set_piece_personality(piece_type, weights)
        return {
            "status": "updated",
            "piece_type": piece_type,
            "weights": weights,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# LLM Model Management

@router.get("/config/models")
async def list_models():
    """List available LLM models with separate supervisor and agent models."""
    orchestrator = get_orchestrator()
    return {
        "supervisor_model": orchestrator.get_supervisor_model(),
        "agent_model": orchestrator.get_agent_model(),
        "available": orchestrator.list_llm_models(),
    }


@router.put("/config/models/supervisor")
async def set_supervisor_model(model: str):
    """Set the LLM model for the supervisor (reasoning model for detailed analysis)."""
    orchestrator = get_orchestrator()
    try:
        orchestrator.set_supervisor_model(model)
        return {
            "status": "updated",
            "supervisor_model": model,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/config/models/agent")
async def set_agent_model(model: str):
    """Set the LLM model for piece agents (faster model for voting)."""
    orchestrator = get_orchestrator()
    try:
        orchestrator.set_agent_model(model)
        return {
            "status": "updated",
            "agent_model": model,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
