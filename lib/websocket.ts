import { isTelemetryEvent, type TelemetryEvent } from '@/types/events'

export type WebSocketStatus = 'connecting' | 'open' | 'closed' | 'error'

type Listener = (event: TelemetryEvent) => void
type StatusListener = (status: WebSocketStatus) => void

export class TelemetrySocket {
  private socket: WebSocket | null = null
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private reconnectAttempts = 0
  private readonly eventListeners = new Set<Listener>()
  private readonly statusListeners = new Set<StatusListener>()
  private manuallyClosed = false
  private lastEventId: string | null = null

  constructor(private readonly url: string, private readonly maxReconnectDelay = 15000) {}

  connect() {
    if (!this.url || typeof window === 'undefined') return
    this.manuallyClosed = false
    this.setStatus('connecting')
    const separator = this.url.includes('?') ? '&' : '?'
    const url = this.lastEventId
      ? `${this.url}${separator}after=${encodeURIComponent(this.lastEventId)}`
      : this.url
    this.socket = new WebSocket(url)
    this.socket.addEventListener('open', () => {
      this.reconnectAttempts = 0
      this.setStatus('open')
    })
    this.socket.addEventListener('message', (message) => {
      try {
        const payload: unknown = JSON.parse(message.data as string)
        if (isTelemetryEvent(payload)) {
          this.lastEventId = payload.id
          this.eventListeners.forEach((listener) => listener(payload))
        }
      } catch {
        // Invalid frames are ignored; telemetry is untrusted input.
      }
    })
    this.socket.addEventListener('error', () => this.setStatus('error'))
    this.socket.addEventListener('close', () => {
      this.setStatus('closed')
      if (!this.manuallyClosed) this.scheduleReconnect()
    })
  }

  close() {
    this.manuallyClosed = true
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer)
    this.socket?.close()
    this.socket = null
  }

  onEvent(listener: Listener) {
    this.eventListeners.add(listener)
    return () => this.eventListeners.delete(listener)
  }

  onStatus(listener: StatusListener) {
    this.statusListeners.add(listener)
    return () => this.statusListeners.delete(listener)
  }

  private scheduleReconnect() {
    if (this.reconnectTimer) return
    const delay = Math.min(1000 * 2 ** this.reconnectAttempts, this.maxReconnectDelay)
    this.reconnectAttempts += 1
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null
      this.connect()
    }, delay)
  }

  private setStatus(status: WebSocketStatus) {
    this.statusListeners.forEach((listener) => listener(status))
  }
}
