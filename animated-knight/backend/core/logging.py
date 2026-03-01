"""Structured logging configuration."""

import logging
import sys
from typing import Any

from .config import get_settings


class StructuredFormatter(logging.Formatter):
    """Simple structured log formatter."""

    def format(self, record: logging.LogRecord) -> str:
        # Add extra fields if present
        extras = ""
        if hasattr(record, "game_id"):
            extras += f" game_id={record.game_id}"
        if hasattr(record, "agent_id"):
            extras += f" agent_id={record.agent_id}"

        base = f"{record.levelname:8} {record.name}: {record.getMessage()}"
        return f"{base}{extras}"


def setup_logging() -> None:
    """Configure application logging."""
    settings = get_settings()

    # Set up root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(settings.log_level)

    # Console handler with structured format
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredFormatter())
    root_logger.addHandler(handler)

    # Reduce noise from third-party libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the given name."""
    return logging.getLogger(name)


class LogContext:
    """Context manager for adding structured fields to log records."""

    def __init__(self, logger: logging.Logger, **kwargs: Any):
        self.logger = logger
        self.kwargs = kwargs
        self.old_factory: Any = None

    def __enter__(self) -> logging.Logger:
        old_factory = logging.getLogRecordFactory()
        self.old_factory = old_factory
        kwargs = self.kwargs

        def record_factory(*args: Any, **record_kwargs: Any) -> logging.LogRecord:
            record = old_factory(*args, **record_kwargs)
            for key, value in kwargs.items():
                setattr(record, key, value)
            return record

        logging.setLogRecordFactory(record_factory)
        return self.logger

    def __exit__(self, *args: Any) -> None:
        if self.old_factory:
            logging.setLogRecordFactory(self.old_factory)
