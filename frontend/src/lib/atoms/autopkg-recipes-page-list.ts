import { atomWithStorage } from 'jotai/utils'
import type { SyncStorage } from 'jotai/vanilla/utils/atomWithStorage'

const STORAGE_KEY = 'munki-manager-autopkg-recipes-page-list-v1'

export type AutopkgRecipesPageListState = {
  search: string
  /** '' = all, 'true' / 'false' = enabled filter */
  enabled: string
  /** '' = all, or a trust status sent as trust_status to the API */
  trustStatus: string
  page: number
  pageSize: number
}

export const defaultAutopkgRecipesPageListState: AutopkgRecipesPageListState = {
  search: '',
  enabled: '',
  trustStatus: '',
  page: 1,
  pageSize: 25,
}

const TRUST_STATUS_VALUES = new Set([
  '',
  'verified',
  'failed',
  'pending_approval',
  'unknown',
])

function safeParseListState(
  raw: string | null,
  initialValue: AutopkgRecipesPageListState,
): AutopkgRecipesPageListState {
  if (raw == null) return initialValue
  try {
    const v: unknown = JSON.parse(raw)
    if (!v || typeof v !== 'object') return initialValue
    const o = v as Record<string, unknown>
    const out: AutopkgRecipesPageListState = {
      ...defaultAutopkgRecipesPageListState,
    }
    if (typeof o.search === 'string') out.search = o.search
    if (o.enabled === 'true' || o.enabled === 'false' || o.enabled === '') {
      out.enabled = o.enabled
    }
    if (
      typeof o.trustStatus === 'string' &&
      TRUST_STATUS_VALUES.has(o.trustStatus)
    ) {
      out.trustStatus = o.trustStatus
    }
    if (typeof o.page === 'number' && o.page >= 1) out.page = o.page
    if (typeof o.pageSize === 'number' && o.pageSize >= 1) {
      out.pageSize = o.pageSize
    }
    return out
  } catch {
    return initialValue
  }
}

const autopkgRecipesPageListStorage: SyncStorage<AutopkgRecipesPageListState> =
  {
    getItem: (key, initialValue) => {
      if (typeof window === 'undefined') {
        return initialValue
      }
      try {
        return safeParseListState(localStorage.getItem(key), initialValue)
      } catch {
        return initialValue
      }
    },
    setItem: (key, newValue) => {
      try {
        localStorage.setItem(key, JSON.stringify(newValue))
      } catch {
        /* ignore */
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

/**
 * AutoPkg recipe overrides list: search, status/trust filters, and pagination. Persisted so
 * values survive navigation and full reload.
 */
export const autopkgRecipesPageListAtom =
  atomWithStorage<AutopkgRecipesPageListState>(
    STORAGE_KEY,
    defaultAutopkgRecipesPageListState,
    autopkgRecipesPageListStorage,
    { getOnInit: true },
  )
