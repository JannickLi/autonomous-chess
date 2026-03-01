"""Configuration management for the Chess Manager."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class TCPConfig:
    """TCP bridge port assignments."""

    bridge_port: int = 9996  # Chess Manager's own ros_bridge_server instance
    robot_port: int = 9999
    perception_port: int = 9997
    agents_port: int = 9998


@dataclass
class WebSocketConfig:
    """WebSocket server configuration."""

    host: str = "0.0.0.0"
    port: int = 8765


@dataclass
class TeacherConfig:
    """Teacher (Stockfish + Mistral) configuration."""

    enabled: bool = True
    stockfish_path: str = "/usr/games/stockfish"
    analysis_depth: int = 20
    model_id: str = "mistral-large-latest"


@dataclass
class VoiceConfig:
    """Voice configuration."""

    enabled: bool = True
    speak_agent_opinions: bool = True
    speak_teacher_feedback: bool = True
    max_opinions_to_speak: int = 3


@dataclass
class GameConfig:
    """Game settings."""

    human_color: str = "white"
    agent_strategy: str = "hybrid"
    parallel_robot_voice: bool = True


@dataclass
class ChessManagerConfig:
    """Top-level Chess Manager configuration."""

    # Timeouts
    perception_timeout_sec: float = 10.0
    agent_timeout_sec: float = 60.0
    robot_timeout_sec: float = 120.0

    # Simulation mode: skip robot execution, just apply moves (default: ROS/hardware mode)
    simulation_mode: bool = False

    # Sub-configs
    tcp: TCPConfig = field(default_factory=TCPConfig)
    websocket: WebSocketConfig = field(default_factory=WebSocketConfig)
    teacher: TeacherConfig = field(default_factory=TeacherConfig)
    voice: VoiceConfig = field(default_factory=VoiceConfig)
    game: GameConfig = field(default_factory=GameConfig)

    @classmethod
    def from_yaml(cls, path: str | Path) -> ChessManagerConfig:
        """Load configuration from a YAML file."""
        path = Path(path)
        if not path.exists():
            return cls()

        with open(path) as f:
            raw = yaml.safe_load(f) or {}

        cm = raw.get("chess_manager", raw)

        tcp_data = cm.get("tcp_ports", {})
        ws_data = cm.get("websocket", {})

        return cls(
            perception_timeout_sec=cm.get("perception_timeout_sec", 10.0),
            agent_timeout_sec=cm.get("agent_timeout_sec", 60.0),
            robot_timeout_sec=cm.get("robot_timeout_sec", 120.0),
            simulation_mode=cm.get("simulation_mode", False),
            tcp=TCPConfig(**tcp_data) if tcp_data else TCPConfig(),
            websocket=WebSocketConfig(**ws_data) if ws_data else WebSocketConfig(),
            teacher=TeacherConfig(
                enabled=cm.get("teacher_enabled", False),
                stockfish_path=cm.get("stockfish_path", "/usr/games/stockfish"),
                analysis_depth=cm.get("analysis_depth", 20),
                model_id=cm.get("teacher_model_id", "mistral-large-latest"),
            ),
            voice=VoiceConfig(
                enabled=cm.get("voice_enabled", False),
                speak_agent_opinions=cm.get("speak_agent_opinions", True),
                speak_teacher_feedback=cm.get("speak_teacher_feedback", True),
                max_opinions_to_speak=cm.get("max_opinions_to_speak", 3),
            ),
            game=GameConfig(
                human_color=cm.get("human_color", "white"),
                agent_strategy=cm.get("agent_strategy", "hybrid"),
                parallel_robot_voice=cm.get("parallel_robot_voice", True),
            ),
        )


# Singleton
_config: Optional[ChessManagerConfig] = None


def get_config(config_path: Optional[str] = None) -> ChessManagerConfig:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        if config_path:
            _config = ChessManagerConfig.from_yaml(config_path)
        else:
            default_path = Path(__file__).parent / "config" / "default.yaml"
            if default_path.exists():
                _config = ChessManagerConfig.from_yaml(default_path)
            else:
                _config = ChessManagerConfig()
    return _config
