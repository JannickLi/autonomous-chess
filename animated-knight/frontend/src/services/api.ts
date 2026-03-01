const API_BASE = '/api'

interface CreateGameOptions {
  fen?: string
  strategy?: string
  whitePlayer?: string
  blackPlayer?: string
}

interface GameResponse {
  id: string
  fen: string
  state: string
  strategy: string
  current_turn: string
  white_player: string
  black_player: string
  is_game_over: boolean
  result: string | null
  is_check: boolean
  legal_moves: string[]
}

interface MoveResponse {
  move: string
  san: string
  fen: string
  is_check: boolean
  is_checkmate: boolean
  is_game_over: boolean
  result: string | null
}

interface AgentMoveResponse {
  move: string
  reasoning: string
  fen: string
  is_check: boolean
  is_checkmate: boolean
  is_game_over: boolean
  result: string | null
  deliberation: {
    proposals: Array<{
      agent_id: string
      description: string
      reasoning: string
      piece_impacts?: Record<string, string>
    }>
    votes: Array<{
      agent_id: string
      voted_for: string  // A, B, or C
      reasoning: string
    }>
    summary: string
  }
}

export async function createGame(options: CreateGameOptions = {}): Promise<GameResponse> {
  const response = await fetch(`${API_BASE}/games`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      fen: options.fen,
      strategy: options.strategy || 'democratic',
      white_player: options.whitePlayer || 'human',
      black_player: options.blackPlayer || 'agent',
    }),
  })

  if (!response.ok) {
    throw new Error('Failed to create game')
  }

  return response.json()
}

export async function getGame(gameId: string): Promise<GameResponse> {
  const response = await fetch(`${API_BASE}/games/${gameId}`)

  if (!response.ok) {
    throw new Error('Failed to get game')
  }

  return response.json()
}

export async function makeMove(gameId: string, move: string): Promise<MoveResponse> {
  const response = await fetch(`${API_BASE}/games/${gameId}/move`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ move }),
  })

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || 'Failed to make move')
  }

  return response.json()
}

export async function requestAgentMove(gameId: string): Promise<AgentMoveResponse> {
  const response = await fetch(`${API_BASE}/games/${gameId}/agent-move`, {
    method: 'POST',
  })

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || 'Failed to get agent move')
  }

  return response.json()
}

export async function getMoveHistory(gameId: string) {
  const response = await fetch(`${API_BASE}/games/${gameId}/history`)

  if (!response.ok) {
    throw new Error('Failed to get move history')
  }

  return response.json()
}

export async function generateMove(fen: string, strategy: string = 'democratic') {
  const response = await fetch(`${API_BASE}/move/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ fen, strategy }),
  })

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || 'Failed to generate move')
  }

  return response.json()
}

export async function getLegalMoves(fen: string) {
  const response = await fetch(`${API_BASE}/move/legal?fen=${encodeURIComponent(fen)}`)

  if (!response.ok) {
    throw new Error('Failed to get legal moves')
  }

  return response.json()
}

export async function getAgentConfig() {
  const response = await fetch(`${API_BASE}/agents/config`)

  if (!response.ok) {
    throw new Error('Failed to get agent config')
  }

  return response.json()
}

export async function getStrategies() {
  const response = await fetch(`${API_BASE}/agents/strategies`)

  if (!response.ok) {
    throw new Error('Failed to get strategies')
  }

  return response.json()
}

// LLM Model management

export interface ModelsResponse {
  supervisor_model: string
  agent_model: string
  available: string[]
}

export async function getModels(): Promise<ModelsResponse> {
  const response = await fetch(`${API_BASE}/games/config/models`)

  if (!response.ok) {
    throw new Error('Failed to get models')
  }

  return response.json()
}

export async function setSupervisorModel(model: string): Promise<{ status: string; supervisor_model: string }> {
  const response = await fetch(`${API_BASE}/games/config/models/supervisor?model=${encodeURIComponent(model)}`, {
    method: 'PUT',
  })

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || 'Failed to set supervisor model')
  }

  return response.json()
}

export async function setAgentModel(model: string): Promise<{ status: string; agent_model: string }> {
  const response = await fetch(`${API_BASE}/games/config/models/agent?model=${encodeURIComponent(model)}`, {
    method: 'PUT',
  })

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || 'Failed to set agent model')
  }

  return response.json()
}

// External services API

export interface ExternalServiceStatus {
  type: 'mock' | 'ros'
  healthy: boolean
  url: string | null
}

export interface ExternalStatusResponse {
  operation_mode: 'simulation' | 'ros'
  detection: ExternalServiceStatus
  robot: ExternalServiceStatus
}

export interface SetModeResponse {
  status: string
  mode: 'simulation' | 'ros'
  using_ros_clients: boolean
}

export interface DetectionResponse {
  success: boolean
  fen: string | null
  pieces: Record<string, string> | null
  error: string | null
}

export interface RobotResponse {
  success: boolean
  error: string | null
}

export async function getExternalStatus(): Promise<ExternalStatusResponse> {
  const response = await fetch(`${API_BASE}/external/status`)

  if (!response.ok) {
    throw new Error('Failed to get external status')
  }

  return response.json()
}

export async function setOperationMode(mode: 'simulation' | 'ros'): Promise<SetModeResponse> {
  const response = await fetch(`${API_BASE}/external/mode`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mode }),
  })

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || 'Failed to set operation mode')
  }

  return response.json()
}

export async function requestDetection(gameId: string): Promise<DetectionResponse> {
  const response = await fetch(`${API_BASE}/external/detect/${gameId}`, {
    method: 'POST',
  })

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || 'Detection failed')
  }

  return response.json()
}

export async function sendRobotMove(gameId: string, move: string, boardFen?: string): Promise<RobotResponse> {
  const response = await fetch(`${API_BASE}/external/robot/${gameId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ move, board_fen: boardFen }),
  })

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || 'Robot execution failed')
  }

  return response.json()
}

export async function homeRobot(gameId: string): Promise<RobotResponse> {
  const response = await fetch(`${API_BASE}/external/robot/${gameId}/home`, {
    method: 'POST',
  })

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || 'Robot home failed')
  }

  return response.json()
}

export async function getExternalHealth(): Promise<{ detection: { healthy: boolean }; robot: { healthy: boolean }; all_healthy: boolean }> {
  const response = await fetch(`${API_BASE}/external/health`)

  if (!response.ok) {
    throw new Error('Failed to get external health')
  }

  return response.json()
}
