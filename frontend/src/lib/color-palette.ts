export type ColorPaletteId = 'gruvbox' | 'monokai' | 'one-dark' | 'catppuccin'

const LEGACY_COLOR_PALETTE_STORAGE_KEY = 'automunki-color-palette'

/** Keep in sync with the inline script in `index.html`. */
export const COLOR_PALETTE_STORAGE_KEY = 'munki-manager-color-palette'

export function normalizeColorPaletteId(value: string | null): ColorPaletteId {
  if (value === 'monokai') return 'monokai'
  if (value === 'one-dark') return 'one-dark'
  if (value === 'catppuccin') return 'catppuccin'
  return 'gruvbox'
}

export function isColorPaletteId(value: string): value is ColorPaletteId {
  return (
    value === 'gruvbox' ||
    value === 'monokai' ||
    value === 'one-dark' ||
    value === 'catppuccin'
  )
}

export function applyColorPaletteToDocument(palette: ColorPaletteId): void {
  if (palette === 'gruvbox') {
    document.documentElement.removeAttribute('data-palette')
  } else {
    document.documentElement.setAttribute('data-palette', palette)
  }
}

export function readStoredColorPalette(): ColorPaletteId {
  try {
    let raw = localStorage.getItem(COLOR_PALETTE_STORAGE_KEY)
    if (raw === null) {
      raw = localStorage.getItem(LEGACY_COLOR_PALETTE_STORAGE_KEY)
      if (raw !== null) {
        localStorage.setItem(COLOR_PALETTE_STORAGE_KEY, raw)
        localStorage.removeItem(LEGACY_COLOR_PALETTE_STORAGE_KEY)
      }
    }
    return normalizeColorPaletteId(raw)
  } catch {
    return 'gruvbox'
  }
}
