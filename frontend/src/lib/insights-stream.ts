import type {
  InsightsHistoryMessage,
  InsightsQueryResponse,
  InsightsTableData,
  InsightsToolUsed,
} from '@/lib/api'
import { redirectToLoginForExpiredAuth } from '@/lib/auth-redirect'
import { publicApiBaseUrl } from '@/lib/public-api-base'

export type InsightsStreamEvent =
  | { type: 'status'; phase: string; message: string; name?: string }
  | {
      type: 'tool'
      name: string
      args: Record<string, unknown>
      summary: string
    }
  | { type: 'text-delta'; delta: string }
  | { type: 'data'; data: InsightsTableData }
  | {
      type: 'done'
      answer: string
      tools_used: InsightsToolUsed[]
      data?: InsightsTableData | null
    }
  | { type: 'error'; message: string }

export type InsightsStreamCallbacks = {
  onStatus?: (message: string) => void
  onTool?: (tool: InsightsToolUsed) => void
  onTextDelta?: (delta: string) => void
  onData?: (data: InsightsTableData) => void
  onDone?: (response: InsightsQueryResponse) => void
  onError?: (message: string) => void
}

function parseSseBuffer(buffer: string): {
  events: InsightsStreamEvent[]
  rest: string
} {
  const events: InsightsStreamEvent[] = []
  const parts = buffer.split('\n\n')
  const rest = parts.pop() ?? ''

  for (const part of parts) {
    for (const line of part.split('\n')) {
      if (!line.startsWith('data: ')) continue
      try {
        events.push(JSON.parse(line.slice(6)) as InsightsStreamEvent)
      } catch {
        // ignore malformed chunks
      }
    }
  }

  return { events, rest }
}

export async function streamInsightsQuery(
  body: { question: string; history: InsightsHistoryMessage[] },
  callbacks: InsightsStreamCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  const token =
    typeof window !== 'undefined' ? localStorage.getItem('token') : null
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    Accept: 'text/event-stream',
  }
  if (token) headers.Authorization = `Bearer ${token}`

  const base = publicApiBaseUrl()
  const res = await fetch(`${base}/api/v1/insights/query/stream`, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
    signal,
  })

  if (res.status === 401) {
    redirectToLoginForExpiredAuth()
    throw new Error('auth-expired-redirecting')
  }

  if (!res.ok) {
    const errBody = await res.json().catch(() => ({ detail: res.statusText }))
    const d = errBody.detail
    const msg =
      typeof d === 'string'
        ? d
        : Array.isArray(d)
          ? d
              .map((x: { msg?: string }) => x?.msg)
              .filter(Boolean)
              .join('; ')
          : res.statusText
    throw new Error(msg || `API error: ${res.status}`)
  }

  if (!res.body) {
    throw new Error('Streaming response has no body')
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const parsed = parseSseBuffer(buffer)
    buffer = parsed.rest

    for (const event of parsed.events) {
      switch (event.type) {
        case 'status':
          callbacks.onStatus?.(event.message)
          break
        case 'tool':
          callbacks.onTool?.({
            name: event.name,
            args: event.args,
            summary: event.summary,
          })
          break
        case 'text-delta':
          callbacks.onTextDelta?.(event.delta)
          break
        case 'data':
          callbacks.onData?.(event.data)
          break
        case 'done':
          callbacks.onDone?.({
            answer: event.answer,
            tools_used: event.tools_used,
            data: event.data ?? null,
          })
          break
        case 'error':
          callbacks.onError?.(event.message)
          break
      }
    }
  }
}
