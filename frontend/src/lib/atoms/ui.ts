import { atomWithStorage, createJSONStorage } from 'jotai/utils'
import type { SyncStorage } from 'jotai/vanilla/utils/atomWithStorage'
import {
  COLOR_PALETTE_STORAGE_KEY,
  type ColorPaletteId,
  readStoredColorPalette,
} from '@/lib/color-palette'

export type ThemePreference = 'light' | 'dark' | 'system'

/** Internal key so next-themes does not read/write the same localStorage entry as Jotai. */
export const THEME_INTERNAL_STORAGE_KEY = 'munki-manager-next-themes'

const THEME_STORAGE_KEY = 'theme'

const themePreferenceStorage: SyncStorage<ThemePreference> = {
  getItem: (key, initialValue) => {
    try {
      const raw = localStorage.getItem(key)
      if (raw == null) return initialValue
      if (raw === 'light' || raw === 'dark' || raw === 'system') return raw
      const parsed = JSON.parse(raw) as unknown
      if (parsed === 'light' || parsed === 'dark' || parsed === 'system') {
        return parsed
      }
    } catch {
      /* ignore */
    }
    return initialValue
  },
  setItem: (key, newValue) => {
    try {
      localStorage.setItem(key, newValue)
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
 * Persists light/dark/system in `theme` (same key next-themes used) so existing sessions keep
 * their preference.
 */
export const themePreferenceAtom = atomWithStorage<ThemePreference>(
  THEME_STORAGE_KEY,
  'system',
  themePreferenceStorage,
  { getOnInit: true },
)

const sidebarStorage = createJSONStorage<boolean>(() => localStorage)

export const sidebarOpenAtom = atomWithStorage<boolean>(
  'munki-manager-sidebar-open',
  true,
  sidebarStorage,
  { getOnInit: true },
)

const colorPaletteJotaiStorage: SyncStorage<ColorPaletteId> = {
  getItem: (key, initialValue) => {
    try {
      if (key !== COLOR_PALETTE_STORAGE_KEY) {
        return initialValue
      }
      return readStoredColorPalette()
    } catch {
      return initialValue
    }
  },
  setItem: (key, newValue) => {
    try {
      localStorage.setItem(key, newValue)
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

export const colorPaletteAtom = atomWithStorage<ColorPaletteId>(
  COLOR_PALETTE_STORAGE_KEY,
  'gruvbox',
  colorPaletteJotaiStorage,
  { getOnInit: true },
)
