"""Data models for the Chess Manager.

These are internal Python dataclasses, NOT ROS2 messages.
Used for communication between Chess Manager submodules.
"""

from __future__ import annotations

import enum
import time
from dataclasses import dataclass, field
from typing import Optional


# ── State Machine ──────────────────────────────────────────────────────────


class GameState(enum.Enum):
    """Chess Manager state machine states."""

    WAITING = "waiting"  # Waiting for game to start
    HUMAN_TURN = "human_turn"  # Waiting for human move
    VALIDATING = "validating"  # Validating detected/spoken move
    AGENT_TURN = "agent_turn"  # Agent's turn, preparing to trigger
    THINKING = "thinking"  # Agents deliberating
    EXECUTING = "executing"  # Robot moving + voice speaking (parallel)
    GAME_OVER = "game_over"  # Game finished


class PlayerColor(enum.Enum):
    """Player color assignment."""

    WHITE = "white"
    BLACK = "black"


# ── Perception ─────────────────────────────────────────────────────────────


@dataclass
class PerceptionResult:
    """Result from the perception system (camera + YOLO detection)."""

    success: bool
    fen: str = ""
    squares: list[str] = field(default_factory=list)
    pieces: dict[str, str] = field(default_factory=dict)
    confidence: float = 0.0
    error: str = ""
    timestamp: float = field(default_factory=time.time)


# ── Move ───────────────────────────────────────────────────────────────────


@dataclass
class MoveRequest:
    """A move to be executed by the robot arm."""

    move_uci: str  # e.g., "e2e4"
    from_square: str = ""
    to_square: str = ""
    piece_type: str = ""
    piece_color: str = ""
    is_capture: bool = False
    captured_piece: str = ""
    is_castling: bool = False
    castling_type: str = ""  # "kingside" or "queenside"
    is_en_passant: bool = False
    is_promotion: bool = False
    promotion_piece: str = ""
    board_fen: str = ""


@dataclass
class MoveResult:
    """Result of a robot move execution."""

    move_uci: str
    success: bool
    error: str = ""
    execution_time_sec: float = 0.0


# ── Agent ──────────────────────────────────────────────────────────────────


@dataclass
class AgentOpinion:
    """Individual agent's opinion on a move."""

    piece_type: str | None  # e.g., "knight", None if unknown
    piece_color: str  # "white" or "black"
    proposed_move: str  # UCI notation
    reasoning: str  # LLM-generated explanation
    confidence: float = 0.0  # 0.0-1.0
    vote_weight: int = 1  # Based on piece value


@dataclass
class AgentDecision:
    """Result of multi-agent deliberation."""

    opinions: list[AgentOpinion] = field(default_factory=list)
    selected_move_uci: str = ""
    selected_move_san: str = ""
    vote_confidence: float = 0.0
    voting_summary: str = ""


# ── Voice ──────────────────────────────────────────────────────────────────


@dataclass
class VoiceCommand:
    """Parsed voice command from VoiceIn."""

    raw_transcript: str  # Full transcription
    parsed_move_uci: str = ""  # Extracted move if recognized
    confidence: float = 0.0  # Recognition confidence
    is_valid_move: bool = False  # Whether it parses as valid chess notation


@dataclass
class SpeakRequest:
    """Request for VoiceOut to speak."""

    content_type: str  # "agent_opinions", "teacher_feedback", "announcement"
    text_to_speak: str  # Pre-formatted text
    priority: int = 0  # Higher = more important


# ── Teacher ────────────────────────────────────────────────────────────────


@dataclass
class TeacherAnalysis:
    """Analysis of a move by the Teacher (Stockfish)."""

    move_uci: str
    move_san: str = ""
    evaluation_category: str = ""  # "brilliant", "good", "inaccuracy", "mistake", "blunder"
    centipawn_loss: float = 0.0
    best_move_uci: str = ""
    best_move_san: str = ""
    explanation: str = ""
    improvement_tips: list[str] = field(default_factory=list)


# ── WebSocket Events ──────────────────────────────────────────────────────


@dataclass
class GameStateEvent:
    """Event pushed to frontends via WebSocket."""

    event_type: str  # "game_state", "teacher_feedback", "voice_recognized", etc.
    data: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
