"""API route modules."""

from .game import router as game_router
from .agents import router as agents_router
from .moves import router as moves_router
from .external import router as external_router

__all__ = ["game_router", "agents_router", "moves_router", "external_router"]
