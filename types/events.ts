export type EventType =
  | 'hacker_command'
  | 'network_event'
  | 'file_access'
  | 'sql_query'
  | 'llm_response'
  | 'session_update'
  | 'security_event'

export interface EventBase {
  id: string
  type: EventType
  timestamp: string
  sessionId?: string
}

export interface HackerCommandEvent extends EventBase {
  type: 'hacker_command'
  command: string
  source?: string
  protocol?: string
}

export interface NetworkEvent extends EventBase {
  type: 'network_event'
  action: string
  source?: string
  destination?: string
  port?: number
  protocol?: string
}

export interface FileAccessEvent extends EventBase {
  type: 'file_access'
  action: 'read' | 'write' | 'list' | 'execute' | string
  path: string
  user?: string
}

export interface SqlQueryEvent extends EventBase {
  type: 'sql_query'
  query: string
  database?: string
  user?: string
}

export interface LlmResponseEvent extends EventBase {
  type: 'llm_response'
  input: string
  response: string
  status: 'queued' | 'generating' | 'complete' | 'error' | string
  streaming?: boolean
  model?: string
}

export interface SessionUpdateEvent extends EventBase {
  type: 'session_update'
  status: 'started' | 'active' | 'ended' | string
  source?: string
  sourceIp?: string
  durationSeconds?: number
}

export interface SecurityEvent extends EventBase {
  type: 'security_event'
  severity: 'low' | 'medium' | 'high' | 'critical' | string
  title: string
  description?: string
}

export type TelemetryEvent =
  | HackerCommandEvent
  | NetworkEvent
  | FileAccessEvent
  | SqlQueryEvent
  | LlmResponseEvent
  | SessionUpdateEvent
  | SecurityEvent

export function isTelemetryEvent(value: unknown): value is TelemetryEvent {
  if (!value || typeof value !== 'object') return false
  const event = value as Partial<EventBase>
  return typeof event.id === 'string' && typeof event.type === 'string' && typeof event.timestamp === 'string'
}
