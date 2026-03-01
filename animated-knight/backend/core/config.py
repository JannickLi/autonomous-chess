"""Application configuration using Pydantic settings."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Server settings
    host: str = Field(default="0.0.0.0", alias="BACKEND_HOST")
    port: int = Field(default=8000, alias="BACKEND_PORT")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO", alias="LOG_LEVEL"
    )

    # LLM Provider API Keys
    mistral_api_key: str = Field(default="", alias="MISTRAL_API_KEY")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")

    # Default LLM settings
    default_llm_provider: str = Field(default="mistral", alias="DEFAULT_LLM_PROVIDER")
    default_llm_model: str = Field(default="mistral-medium", alias="DEFAULT_LLM_MODEL")
    default_temperature: float = Field(default=0.7, alias="DEFAULT_TEMPERATURE")

    # Separate model settings for supervisor and agents
    supervisor_llm_model: str = Field(default="mistral-medium-latest", alias="SUPERVISOR_LLM_MODEL")
    agent_llm_model: str = Field(default="mistral-small-latest", alias="AGENT_LLM_MODEL")

    # CORS settings (for frontend)
    cors_origins: list[str] = Field(default=["http://localhost:5173", "http://localhost:3000"])

    # Stockfish engine settings
    stockfish_path: str | None = Field(default=None, alias="STOCKFISH_PATH")
    stockfish_depth: int = Field(default=20, alias="STOCKFISH_DEPTH")
    stockfish_time_limit_ms: int = Field(default=5000, alias="STOCKFISH_TIME_LIMIT_MS")
    use_engine: bool = Field(default=True, alias="USE_ENGINE")

    # External API settings for camera detection and robot control
    # Modes: "simulation" (mock), "ros" (ROS topics via TCP bridge)
    operation_mode: Literal["simulation", "ros"] = Field(
        default="simulation", alias="OPERATION_MODE"
    )

    # ROS TCP bridge (used when OPERATION_MODE=ros and ROS_TCP_HOST is set)
    # Run ros_bridge_server.py with system Python + ROS2 sourced, then point here
    ros_tcp_host: str | None = Field(default=None, alias="ROS_TCP_HOST")
    ros_tcp_port: int = Field(default=9998, alias="ROS_TCP_PORT")

    # ROS configuration (used when operation_mode="ros")
    # Board perception topics
    ros_capture_topic: str = Field(default="/chess/capture", alias="ROS_CAPTURE_TOPIC")
    ros_position_topic: str = Field(default="/chess/perception_result", alias="ROS_POSITION_TOPIC")
    ros_detection_status_topic: str = Field(default="/chess/perception_status", alias="ROS_DETECTION_STATUS_TOPIC")

    # Move execution topics
    ros_move_topic: str = Field(default="/chess/move_request", alias="ROS_MOVE_TOPIC")
    ros_move_result_topic: str = Field(default="/chess/move_result", alias="ROS_MOVE_RESULT_TOPIC")
    ros_robot_home_topic: str = Field(default="/chess/robot/home", alias="ROS_ROBOT_HOME_TOPIC")
    ros_robot_status_topic: str = Field(default="/chess/robot/status", alias="ROS_ROBOT_STATUS_TOPIC")

    # Agent deliberation topics
    ros_agent_request_topic: str = Field(default="/chess/agent_request", alias="ROS_AGENT_REQUEST_TOPIC")
    ros_agent_opinions_topic: str = Field(default="/chess/agent_opinions", alias="ROS_AGENT_OPINIONS_TOPIC")

    # Camera topic (for debugging/visualization)
    ros_cam_topic: str = Field(default="/camera1/image_path", alias="ROS_CAM_TOPIC")

    # Timeouts
    ros_detection_timeout: float = Field(default=10.0, alias="ROS_DETECTION_TIMEOUT")
    ros_move_timeout: float = Field(default=60.0, alias="ROS_MOVE_TIMEOUT")


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
