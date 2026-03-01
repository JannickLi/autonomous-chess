"""Main FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from backend.core import get_settings, setup_logging
from backend.api.routes import game_router, agents_router, moves_router, external_router
from backend.api.websocket import websocket_endpoint
from backend.external.manager import get_external_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    import asyncio

    setup_logging()
    manager = get_external_manager()  # Eagerly init so ROS/TCP bridge connects at startup

    # Give the agent listener the running event loop so it can schedule
    # async orchestrator calls from the bridge reader thread.
    if manager._agent_listener is not None:
        manager._agent_listener.set_loop(asyncio.get_running_loop())

    yield


app = FastAPI(
    title="Chess Agents API",
    description="Multi-agent LLM chess system",
    version="0.1.0",
    lifespan=lifespan,
)

# Configure CORS
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(game_router)
app.include_router(agents_router)
app.include_router(moves_router)
app.include_router(external_router)


# WebSocket endpoint
@app.websocket("/ws")
async def websocket_route(websocket: WebSocket):
    """WebSocket endpoint for real-time updates."""
    await websocket_endpoint(websocket)


@app.websocket("/ws/{game_id}")
async def websocket_game_route(websocket: WebSocket, game_id: str):
    """WebSocket endpoint for a specific game."""
    await websocket_endpoint(websocket, game_id)


# Health check
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "version": "0.1.0"}


@app.get("/")
async def root():
    """Root endpoint with API info."""
    return {
        "name": "Chess Agents API",
        "version": "0.1.0",
        "docs": "/docs",
        "endpoints": {
            "games": "/api/games",
            "moves": "/api/move",
            "agents": "/api/agents",
            "external": "/api/external",
            "websocket": "/ws",
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
