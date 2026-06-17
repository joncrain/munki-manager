import { useAtom } from 'jotai'
import { useCallback, useRef, useState } from 'react'
import type {
  InsightsHistoryMessage,
  InsightsQueryResponse,
  InsightsToolUsed,
} from '@/lib/api'
import {
  type InsightsChatSession,
  insightsChatSessionAtom,
} from '@/lib/atoms/insights-chat'
import { streamInsightsQuery } from '@/lib/insights-stream'

export type InsightsChatMessage = InsightsHistoryMessage & {
  id: string
  toolsUsed?: InsightsToolUsed[]
  tableData?: InsightsQueryResponse['data']
  statusMessage?: string
}

export type InsightsChatStatus = 'ready' | 'submitted' | 'streaming' | 'error'

export function useInsightsChat() {
  const [session, setSession] = useAtom(insightsChatSessionAtom)
  const messages = session.messages
  const [status, setStatus] = useState<InsightsChatStatus>('ready')
  const [error, setError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  const setMessages = useCallback(
    (
      updater:
        | InsightsChatMessage[]
        | ((prev: InsightsChatMessage[]) => InsightsChatMessage[]),
    ) => {
      setSession((prev: InsightsChatSession) => {
        const nextMessages =
          typeof updater === 'function' ? updater(prev.messages) : updater
        return {
          messages: nextMessages,
          updatedAt: new Date().toISOString(),
        }
      })
    },
    [setSession],
  )

  const stop = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
    setStatus('ready')
  }, [])

  const sendMessage = useCallback(
    async (text: string) => {
      const trimmed = text.trim()
      if (!trimmed || status === 'submitted' || status === 'streaming') return

      setError(null)
      setStatus('submitted')

      const userId = crypto.randomUUID()
      const assistantId = crypto.randomUUID()
      const history: InsightsHistoryMessage[] = messages.map(
        ({ role, content }) => ({
          role,
          content,
        }),
      )

      setMessages((prev) => [
        ...prev,
        { id: userId, role: 'user', content: trimmed },
        {
          id: assistantId,
          role: 'assistant',
          content: '',
          toolsUsed: [],
          tableData: null,
        },
      ])

      abortRef.current = new AbortController()
      let streamed = ''

      const patchAssistant = (patch: Partial<InsightsChatMessage>) => {
        setMessages((prev) =>
          prev.map((m) => (m.id === assistantId ? { ...m, ...patch } : m)),
        )
      }

      try {
        setStatus('streaming')

        await streamInsightsQuery(
          { question: trimmed, history },
          {
            onStatus: (message) => {
              patchAssistant({ statusMessage: message })
            },
            onTool: (tool) => {
              setMessages((prev) =>
                prev.map((m) => {
                  if (m.id !== assistantId) return m
                  const toolsUsed = [...(m.toolsUsed ?? []), tool]
                  return { ...m, toolsUsed, statusMessage: tool.summary }
                }),
              )
            },
            onTextDelta: (delta) => {
              streamed += delta
              patchAssistant({ content: streamed, statusMessage: undefined })
            },
            onData: (data) => {
              patchAssistant({ tableData: data })
            },
            onDone: (response: InsightsQueryResponse) => {
              patchAssistant({
                content: response.answer || streamed,
                toolsUsed: response.tools_used,
                tableData: response.data ?? undefined,
                statusMessage: undefined,
              })
            },
            onError: (message) => {
              setError(message)
              setStatus('error')
            },
          },
          abortRef.current.signal,
        )

        setStatus('ready')
      } catch (err) {
        if (err instanceof Error && err.name === 'AbortError') {
          setStatus('ready')
          return
        }
        const message =
          err instanceof Error ? err.message : 'Something went wrong.'
        if (
          message.includes('not configured') ||
          message.includes('INSIGHTS_ENABLED')
        ) {
          setError('not-configured')
        } else {
          setError(message)
        }
        setStatus('error')
        patchAssistant({
          content: streamed || 'Request failed.',
          statusMessage: undefined,
        })
      } finally {
        abortRef.current = null
      }
    },
    [messages, setMessages, status],
  )

  const clearConversation = useCallback(() => {
    stop()
    setSession({ messages: [], updatedAt: new Date().toISOString() })
    setError(null)
    setStatus('ready')
  }, [setSession, stop])

  return {
    messages,
    sendMessage,
    clearConversation,
    status,
    error,
    stop,
    isLoading: status === 'submitted' || status === 'streaming',
  }
}
