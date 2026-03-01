"""Agent module for chess-playing AI agents."""

from .base import AgentConfig, BaseAgent, MoveProposal, Vote
from .personality import (
    PersonalityWeights,
    get_personality_for_piece,
    load_personality_preset,
    PIECE_PERSONALITIES,
    PERSONALITY_PRESETS,
)
from .piece_agent import PieceAgent
from .supervisor_agent import SupervisorAgent

__all__ = [
    "AgentConfig",
    "BaseAgent",
    "MoveProposal",
    "Vote",
    "PersonalityWeights",
    "get_personality_for_piece",
    "load_personality_preset",
    "PIECE_PERSONALITIES",
    "PERSONALITY_PRESETS",
    "PieceAgent",
    "SupervisorAgent",
]
