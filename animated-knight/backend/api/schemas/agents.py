"""Schemas for agent configuration endpoints."""

from typing import Any

from pydantic import BaseModel, Field


class LLMConfigSchema(BaseModel):
    """LLM configuration."""

    provider: str = Field(default="mistral", description="LLM provider name")
    model: str = Field(default="mistral-medium", description="Model identifier")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1024, ge=1)


class PieceWeightsSchema(BaseModel):
    """Voting weights for each piece type."""

    king: int = Field(default=10, ge=1)
    queen: int = Field(default=9, ge=1)
    rook: int = Field(default=5, ge=1)
    bishop: int = Field(default=3, ge=1)
    knight: int = Field(default=3, ge=1)
    pawn: int = Field(default=1, ge=1)


class StrategyConfigSchema(BaseModel):
    """Configuration for a specific strategy."""

    name: str
    enabled: bool = True
    llm: LLMConfigSchema = Field(default_factory=LLMConfigSchema)
    piece_weights: PieceWeightsSchema | None = None  # Only for democratic


class AgentConfigResponse(BaseModel):
    """Current agent configuration."""

    default_strategy: str
    available_strategies: list[str]
    strategies: dict[str, StrategyConfigSchema]
    llm_defaults: LLMConfigSchema


class UpdateAgentConfigRequest(BaseModel):
    """Request to update agent configuration."""

    default_strategy: str | None = None
    llm_defaults: LLMConfigSchema | None = None
    strategy_config: dict[str, Any] | None = None


class UpdatePromptRequest(BaseModel):
    """Request to update a prompt template."""

    template: str = Field(description="The new prompt template")


class PromptResponse(BaseModel):
    """Response with a prompt template."""

    piece_type: str
    template: str
