/**
 * WebSocket client for Chess Manager.
 *
 * Connects to the chess_manager WebSocket server (default ws://localhost:8765)
 * and dispatches events to the Zustand store.
 */

import { useGameStore } from '../stores/gameStore'

const WS_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:8765'
const RECONNECT_DELAY_MS = 2000

let ws: WebSocket | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let intentionalClose = false

export function connect(): void {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
    return
  }

  intentionalClose = false
  const store = useGameStore.getState()
  store.setConnecting(true)

  ws = new WebSocket(WS_URL)

  ws.onopen = () => {
    const s = useGameStore.getState()
    s.setConnected(true)
    s.setConnecting(false)
    s.setError(null)
    // Request initial status
    sendCommand('status')
  }

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data)
      handleMessage(msg)
    } catch {
      console.error('Failed to parse WS message:', event.data)
    }
  }

  ws.onclose = () => {
    const s = useGameStore.getState()
    s.setConnected(false)
    s.setConnecting(false)
    ws = null

    if (!intentionalClose) {
      scheduleReconnect()
    }
  }

  ws.onerror = () => {
    // onclose will fire after this
  }
}

export function disconnect(): void {
  intentionalClose = true
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
  if (ws) {
    ws.close()
    ws = null
  }
  const s = useGameStore.getState()
  s.setConnected(false)
  s.setConnecting(false)
}

export function sendCommand(type: string, data?: Record<string, unknown>): void {
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    console.warn('WebSocket not connected, cannot send:', type)
    return
  }
  ws.send(JSON.stringify({ type, ...data }))
}

function scheduleReconnect(): void {
  if (reconnectTimer) return
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null
    connect()
  }, RECONNECT_DELAY_MS)
}

function handleMessage(msg: Record<string, unknown>): void {
  const store = useGameStore.getState()
  const type = msg.type as string

  console.debug('[WS] received:', type, msg)

  switch (type) {
    case 'connected':
      // Server confirmed connection
      break

    case 'game_state':
      console.debug('[WS] game_state data:', msg.data)
      store.updateFromEvent(msg.data as Record<string, unknown>)
      break

    case 'agent_deliberation':
      console.debug('[WS] agent_deliberation data:', JSON.stringify(msg.data, null, 2))
      store.setDeliberation(msg.data as Record<string, unknown>)
      break

    case 'status':
      console.debug('[WS] status data:', msg.data)
      store.updateFromEvent(msg.data as Record<string, unknown>)
      break

    case 'error':
      console.debug('[WS] error:', msg.message)
      store.setError(msg.message as string)
      break

    case 'voice_status':
      console.debug('[WS] voice_status data:', msg.data)
      store.setVoiceStatus(msg.data as Record<string, unknown>)
      break

    case 'pong':
      break

    default:
      console.warn('Unknown WS message type:', type)
  }
}
