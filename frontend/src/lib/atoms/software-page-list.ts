import type { SortingState } from '@tanstack/react-table'
import { atomWithStorage } from 'jotai/utils'
import type { SyncStorage } from 'jotai/vanilla/utils/atomWithStorage'

const STORAGE_KEY = 'munki-manager-software-page-list-v2'

export type SoftwarePageListState = {
  search: string
  category: string
  catalog: string
  latestOnly: boolean
  page: number
  pageSize: number
  sorting: SortingState
}

export const defaultSoftwarePageListState: SoftwarePageListState = {
  search: '',
  category: '',
  catalog: '',
  latestOnly: true,
  page: 1,
  pageSize: 50,
  sorting: [{ id: 'display_name', desc: false }],
}

function safeParseListState(
  raw: string | null,
  initialValue: SoftwarePageListState,
): SoftwarePageListState {
  if (raw == null) return initialValue
  try {
    const v: unknown = JSON.parse(raw)
    if (!v || typeof v !== 'object') return initialValue
    const o = v as Record<string, unknown>
    const out: SoftwarePageListState = { ...defaultSoftwarePageListState }
    if (typeof o.search === 'string') out.search = o.search
    if (typeof o.category === 'string') out.category = o.category
    if (typeof o.catalog === 'string') out.catalog = o.catalog
    if (typeof o.latestOnly === 'boolean') out.latestOnly = o.latestOnly
    if (typeof o.page === 'number' && o.page >= 1) out.page = o.page
    if (typeof o.pageSize === 'number' && o.pageSize >= 1)
      out.pageSize = o.pageSize
    if (Array.isArray(o.sorting) && o.sorting.length > 0) {
      out.sorting = o.sorting.map((s) => {
        const row = s as { id?: unknown; desc?: unknown }
        return {
          id: typeof row.id === 'string' ? row.id : 'display_name',
          desc: !!row.desc,
        }
      })
    }
    return out
  } catch {
    return initialValue
  }
}

const softwarePageListStorage: SyncStorage<SoftwarePageListState> = {
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
 * Software catalog list: search, filters, page, and sort. Persisted so values survive
 * navigation away and back (and full reload).
 */
export const softwarePageListAtom = atomWithStorage<SoftwarePageListState>(
  STORAGE_KEY,
  defaultSoftwarePageListState,
  softwarePageListStorage,
  { getOnInit: true },
)
