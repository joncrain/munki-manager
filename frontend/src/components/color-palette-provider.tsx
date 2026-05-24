import { useAtom } from 'jotai'
import { createContext, useContext, useEffect, useMemo } from 'react'
import { colorPaletteAtom } from '@/lib/atoms/ui'
import {
  applyColorPaletteToDocument,
  type ColorPaletteId,
} from '@/lib/color-palette'

type ColorPaletteContextValue = {
  palette: ColorPaletteId
  setPalette: (palette: ColorPaletteId) => void
}

const ColorPaletteContext = createContext<ColorPaletteContextValue | null>(null)

export function ColorPaletteProvider({
  children,
}: {
  children: React.ReactNode
}) {
  const [palette, setPalette] = useAtom(colorPaletteAtom)

  useEffect(() => {
    applyColorPaletteToDocument(palette)
  }, [palette])

  const value = useMemo(() => ({ palette, setPalette }), [palette, setPalette])

  return (
    <ColorPaletteContext.Provider value={value}>
      {children}
    </ColorPaletteContext.Provider>
  )
}

export function useColorPalette(): ColorPaletteContextValue {
  const ctx = useContext(ColorPaletteContext)
  if (!ctx) {
    throw new Error(
      'useColorPalette must be used within a ColorPaletteProvider',
    )
  }
  return ctx
}
