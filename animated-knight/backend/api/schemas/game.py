"""Schemas for game-related API endpoints."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class CreateGameRequest(BaseModel):
    """Request to create a new game."""

    fen: str | None = Field(
        default=None,
        description="Starting FEN position. If not provided, uses standard starting position.",
    )
    strategy: str = Field(
        default="hybrid",
        description="Agent decision strategy: 'hybrid' (democratic) or 'supervisor'",
    )
    white_player: Literal["human", "agent"] = Field(
        default="human",
        description="Who plays white",
    )
    black_player: Literal["human", "agent"] = Field(
        default="agent",
        description="Who plays black",
    )


class CreateGameResponse(BaseModel):
    """Response after creating a game."""

    id: str
    fen: str
    state: str
    strategy: str
    current_turn: str
    white_player: str
    black_player: str


class GameResponse(BaseModel):
    """Full game state response."""

    id: str
    fen: str
    state: str
    strategy: str
    current_turn: str
    white_player: str
    black_player: str
    is_game_over: bool
    result: str | None
    move_count: int
    is_check: bool
    legal_moves: list[str]
    created_at: str
    updated_at: str


class MakeMoveRequest(BaseModel):
    """Request to make a move."""

    move: str = Field(
        description="Move in UCI notation (e.g., 'e2e4') or SAN notation (e.g., 'e4')"
    )


class MakeMoveResponse(BaseModel):
    """Response after making a move."""

    move: str
    san: str
    fen: str
    is_check: bool
    is_checkmate: bool
    is_game_over: bool
    result: str | None = None


class MoveHistoryEntry(BaseModel):
    """A single move in the history."""

    move_number: int
    color: str
    move: str
    san: str
    timestamp: str
    has_deliberation: bool


class MoveHistoryResponse(BaseModel):
    """Response with move history."""

    game_id: str
    moves: list[MoveHistoryEntry]
    total_moves: int
