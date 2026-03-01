"""Pydantic schemas for API requests and responses."""

from .game import (
    CreateGameRequest,
    CreateGameResponse,
    GameResponse,
    MakeMoveRequest,
    MakeMoveResponse,
    MoveHistoryResponse,
)
from .agents import (
    AgentConfigResponse,
    UpdateAgentConfigRequest,
    UpdatePromptRequest,
    LLMConfigSchema,
    StrategyConfigSchema,
    PieceWeightsSchema,
)
from .moves import (
    GenerateMoveRequest,
    GenerateMoveResponse,
    ProposalResponse,
    DeliberationResponse,
)

__all__ = [
    "CreateGameRequest",
    "CreateGameResponse",
    "GameResponse",
    "MakeMoveRequest",
    "MakeMoveResponse",
    "MoveHistoryResponse",
    "AgentConfigResponse",
    "UpdateAgentConfigRequest",
    "UpdatePromptRequest",
    "LLMConfigSchema",
    "StrategyConfigSchema",
    "PieceWeightsSchema",
    "GenerateMoveRequest",
    "GenerateMoveResponse",
    "ProposalResponse",
    "DeliberationResponse",
]
