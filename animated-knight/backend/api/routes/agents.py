"""Agent configuration API routes."""

from fastapi import APIRouter, HTTPException

from backend.orchestration import get_orchestrator
from backend.core import get_settings
from backend.api.schemas import (
    AgentConfigResponse,
    UpdateAgentConfigRequest,
    UpdatePromptRequest,
    LLMConfigSchema,
    StrategyConfigSchema,
    PieceWeightsSchema,
)

router = APIRouter(prefix="/api/agents", tags=["agents"])

# In-memory config store (would be persisted in production)
_config_store = {
    "default_strategy": "democratic",
    "prompts": {},
}


@router.get("/config", response_model=AgentConfigResponse)
async def get_agent_config():
    """Get current agent configuration."""
    orchestrator = get_orchestrator()
    settings = get_settings()

    strategies = orchestrator.list_strategies()

    # Build strategy configs
    strategy_configs = {}
    for name in strategies:
        config = StrategyConfigSchema(
            name=name,
            enabled=True,
            llm=LLMConfigSchema(
                provider=settings.default_llm_provider,
                model=settings.default_llm_model,
                temperature=settings.default_temperature,
            ),
        )
        if name == "democratic":
            config.piece_weights = PieceWeightsSchema()
        strategy_configs[name] = config

    return AgentConfigResponse(
        default_strategy=_config_store["default_strategy"],
        available_strategies=strategies,
        strategies=strategy_configs,
        llm_defaults=LLMConfigSchema(
            provider=settings.default_llm_provider,
            model=settings.default_llm_model,
            temperature=settings.default_temperature,
        ),
    )


@router.put("/config")
async def update_agent_config(request: UpdateAgentConfigRequest):
    """Update agent configuration."""
    orchestrator = get_orchestrator()

    if request.default_strategy:
        if request.default_strategy not in orchestrator.list_strategies():
            raise HTTPException(
                status_code=400,
                detail=f"Unknown strategy: {request.default_strategy}",
            )
        _config_store["default_strategy"] = request.default_strategy

    return {"status": "updated", "config": _config_store}


@router.get("/prompts")
async def list_prompts():
    """List all custom prompts."""
    return {"prompts": _config_store["prompts"]}


@router.get("/prompts/{piece_type}")
async def get_prompt(piece_type: str):
    """Get prompt template for a piece type."""
    valid_pieces = ["pawn", "knight", "bishop", "rook", "queen", "king", "supervisor"]
    if piece_type not in valid_pieces:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid piece type. Valid types: {valid_pieces}",
        )

    template = _config_store["prompts"].get(piece_type)
    if not template:
        return {"piece_type": piece_type, "template": None, "is_default": True}

    return {"piece_type": piece_type, "template": template, "is_default": False}


@router.put("/prompts/{piece_type}")
async def update_prompt(piece_type: str, request: UpdatePromptRequest):
    """Update prompt template for a piece type."""
    valid_pieces = ["pawn", "knight", "bishop", "rook", "queen", "king", "supervisor"]
    if piece_type not in valid_pieces:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid piece type. Valid types: {valid_pieces}",
        )

    _config_store["prompts"][piece_type] = request.template
    return {"status": "updated", "piece_type": piece_type}


@router.delete("/prompts/{piece_type}")
async def reset_prompt(piece_type: str):
    """Reset prompt to default."""
    if piece_type in _config_store["prompts"]:
        del _config_store["prompts"][piece_type]
    return {"status": "reset", "piece_type": piece_type}


@router.get("/strategies")
async def list_strategies():
    """List available decision strategies."""
    orchestrator = get_orchestrator()
    strategies = orchestrator.list_strategies()

    return {
        "strategies": [
            {
                "name": s,
                "description": _get_strategy_description(s),
            }
            for s in strategies
        ],
        "default": _config_store["default_strategy"],
    }


def _get_strategy_description(name: str) -> str:
    """Get description for a strategy."""
    descriptions = {
        "democratic": "Each movable piece proposes a move, all pieces vote, majority wins (weighted by piece value)",
        "supervisor": "A supervisor agent coordinates piece agents and makes the final decision",
        "hybrid": "Supervisor proposes top 3 candidates, then all pieces vote on them",
    }
    return descriptions.get(name, "No description available")
