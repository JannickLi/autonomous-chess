# Chess Agents

A multi-agent LLM chess system where AI-powered agents collaborate to play chess, with a web frontend for visualization, configuration, and gameplay.

## Features

- **Multi-Agent Deliberation**: Watch AI agents discuss and decide on moves
- **Multiple Strategies**:
  - **Democratic**: Each piece proposes moves, all pieces vote (weighted by piece value)
  - **Supervisor**: A central agent coordinates piece agents and makes final decisions
- **Real-time Streaming**: See agent thoughts as they happen via WebSocket
- **Configurable Prompts**: Customize agent behavior through prompt templates
- **Multiple LLM Providers**: Support for Mistral, OpenAI, and Anthropic

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- An API key for at least one LLM provider (Mistral, OpenAI, or Anthropic)

### Setup

1. **Clone and setup environment:**

```bash
cp .env.example .env
# Edit .env and add your API keys
```

2. **Install backend dependencies:**

```bash
cd backend
pip install -e .
```

3. **Install frontend dependencies:**

```bash
cd frontend
npm install
```

4. **Start the backend:**

```bash
cd backend
python -m uvicorn backend.main:app --reload
```

5. **Start the frontend:**

```bash
cd frontend
npm run dev
```

6. **Open the app:**

Navigate to http://localhost:5173

## API Documentation

Once the backend is running, visit http://localhost:8000/docs for the interactive API documentation.

### Key Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/games` | POST | Create a new game |
| `/api/games/{id}` | GET | Get game state |
| `/api/games/{id}/move` | POST | Make a player move |
| `/api/games/{id}/agent-move` | POST | Request agent move |
| `/api/move/generate` | POST | Generate move for any position (external API) |
| `/api/agents/config` | GET/PUT | Agent configuration |
| `/ws/{game_id}` | WS | Real-time game updates |

### External API Example

Generate a move for any position:

```bash
curl -X POST http://localhost:8000/api/move/generate \
  -H "Content-Type: application/json" \
  -d '{
    "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
    "strategy": "democratic"
  }'
```

## Architecture

```
┌─────────────────┐     ┌─────────────────┐
│    Frontend     │────▶│    Backend      │
│  React + Vite   │◀────│    FastAPI      │
└─────────────────┘     └─────────────────┘
                               │
                    ┌──────────┴──────────┐
                    ▼                     ▼
            ┌───────────────┐    ┌───────────────┐
            │  Orchestrator │    │  WebSocket    │
            └───────┬───────┘    │   Manager     │
                    │            └───────────────┘
         ┌──────────┴──────────┐
         ▼                     ▼
  ┌─────────────┐      ┌─────────────┐
  │  Democratic │      │  Supervisor │
  │  Strategy   │      │  Strategy   │
  └─────────────┘      └─────────────┘
         │                     │
         ▼                     ▼
  ┌─────────────┐      ┌─────────────┐
  │ Piece Agents│      │ Supervisor  │
  │ (per piece) │      │   Agent     │
  └─────────────┘      └─────────────┘
         │                     │
         └──────────┬──────────┘
                    ▼
            ┌───────────────┐
            │  LLM Provider │
            │   Registry    │
            └───────────────┘
```

## Hardware Integration

The system supports integration with physical chess boards via camera detection and robot control.

### Operation Modes

| Mode | Description | Use Case |
|------|-------------|----------|
| `simulation` | Mock detection/robot (default) | Development, testing |
| `real` | HTTP API communication | Standalone hardware services |
| `ros` | ROS topic communication | Integrated robotics system |

### Running in Simulation Mode

No additional setup required - this is the default:

```bash
export OPERATION_MODE=simulation  # optional, this is default
python -m uvicorn backend.main:app --reload
```

### Running with ROS Integration

Requires ROS installation and the detection/robot nodes running:

```bash
export OPERATION_MODE=ros
export ROS_MASTER_URI=http://localhost:11311
python -m uvicorn backend.main:app --reload
```

See `docs/ROS_ARCHITECTURE.md` for the full ROS integration architecture.

## Configuration

### Agent Strategies

Configure strategies in `configs/agents/`:

```yaml
# configs/agents/democratic.yaml
strategy: democratic
voting:
  method: weighted
  weights:
    king: 10
    queen: 9
    rook: 5
    bishop: 3
    knight: 3
    pawn: 1
```

### Prompt Templates

Customize agent prompts in `configs/prompts/`:

```yaml
# configs/prompts/piece_base.yaml
template: |
  You are the {piece_name} on {square}...
```

## Development

### Running Tests

```bash
cd backend
pytest
```

### Code Style

```bash
# Backend
cd backend
ruff check .
mypy .

# Frontend
cd frontend
npm run lint
```

## Project Structure

```
chess-agents/
├── backend/
│   ├── api/           # REST and WebSocket endpoints
│   ├── agents/        # Agent implementations
│   ├── chess_engine/  # Chess logic wrapper
│   ├── llm/           # LLM provider abstraction
│   ├── orchestration/ # Game session management
│   └── external/      # Hardware integration
│       ├── detection/ # Camera detection clients
│       ├── robot/     # Robot control clients
│       └── ros/       # ROS integration (topic-based)
├── frontend/
│   ├── src/
│   │   ├── components/  # React components
│   │   ├── stores/      # Zustand state stores
│   │   └── services/    # API and WebSocket services
├── configs/           # YAML configuration files
└── docs/              # Architecture documentation
```

## License

MIT
