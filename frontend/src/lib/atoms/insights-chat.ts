import { atomWithStorage, createJSONStorage } from 'jotai/utils'
import type { SyncStorage } from 'jotai/vanilla/utils/atomWithStorage'
import type { InsightsChatMessage } from '@/hooks/use-insights-chat'

export type InsightsChatSession = {
  messages: InsightsChatMessage[]
  updatedAt: string
}

const MAX_STORED_MESSAGES = 50

function trimSession(session: InsightsChatSession): InsightsChatSession {
  if (session.messages.length <= MAX_STORED_MESSAGES) return session
  return {
    ...session,
    messages: session.messages.slice(-MAX_STORED_MESSAGES),
  }
}

const insightsChatStorage: SyncStorage<InsightsChatSession> = {
  getItem: (key, initialValue) => {
    try {
      const raw = localStorage.getItem(key)
      if (!raw) return initialValue
      const parsed = JSON.parse(raw) as InsightsChatSession
      if (!parsed || !Array.isArray(parsed.messages)) return initialValue
      return trimSession(parsed)
    } catch {
      return initialValue
    }
  },
  setItem: (key, newValue) => {
    try {
      localStorage.setItem(key, JSON.stringify(trimSession(newValue)))
    } catch {
      /* ignore quota errors */
    }
  },
  removeItem: (key) => {
    try {
      localStorage.removeItem(key)
    } catch {
      /* ignore */
    }
  },
}

export const insightsChatSessionAtom = atomWithStorage<InsightsChatSession>(
  'munki-manager-insights-chat',
  { messages: [], updatedAt: '' },
  insightsChatStorage,
  { getOnInit: true },
)

export const insightsDataPanelOpenAtom = atomWithStorage<boolean>(
  'munki-manager-insights-data-panel-open',
  true,
  createJSONStorage(() => localStorage),
  { getOnInit: true },
)

export const insightsChatInputAtom = atomWithStorage<string>(
  'munki-manager-insights-chat-input',
  '',
  createJSONStorage(() => localStorage),
  { getOnInit: true },
)
