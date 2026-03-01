"""Schemas for move generation endpoints."""

from pydantic import BaseModel, Field


class GenerateMoveRequest(BaseModel):
    """Request to generate a move for a position."""

    fen: str = Field(description="Chess position in FEN notation")
    strategy: str = Field(
        default="hybrid",
        description="Decision strategy to use (hybrid or supervisor)",
    )


class ProposalResponse(BaseModel):
    """A move proposal from an agent with strategic description."""

    agent_id: str
    description: str  # Strategic description of the move
    reasoning: str
    piece_type: str | None = None
    piece_square: str | None = None
    piece_impacts: dict[str, str] | None = None  # Impact on each piece


class VoteResponse(BaseModel):
    """A vote cast by an agent (A, B, or C)."""

    agent_id: str
    voted_for: str  # A, B, or C
    reasoning: str | None = None


class DeliberationResponse(BaseModel):
    """Deliberation details for a move."""

    proposals: list[ProposalResponse]
    votes: list[VoteResponse] | None = None
    summary: str


class GenerateMoveResponse(BaseModel):
    """Response from move generation."""

    move: str
    reasoning: str
    deliberation: DeliberationResponse
