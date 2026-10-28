'use client'

import { useEffect, useMemo, useState } from 'react'
import { TelemetrySocket, type WebSocketStatus } from '@/lib/websocket'
import type { TelemetryEvent } from '@/types/events'

const MAX_EVENTS = 100

export function useWebSocket(url = process.env.NEXT_PUBLIC_WS_URL ?? '') {
  const [status, setStatus] = useState<WebSocketStatus>(url ? 'connecting' : 'closed')
  const [events, setEvents] = useState<TelemetryEvent[]>([])
  const socket = useMemo(() => (url ? new TelemetrySocket(url) : null), [url])

  useEffect(() => {
    if (!socket) return
    const removeEventListener = socket.onEvent((event) => setEvents((current) => [event, ...current].slice(0, MAX_EVENTS)))
    const removeStatusListener = socket.onStatus(setStatus)
    socket.connect()
    return () => {
      removeEventListener()
      removeStatusListener()
      socket.close()
    }
  }, [socket])

  return { status, events, isConfigured: Boolean(url) }
}
