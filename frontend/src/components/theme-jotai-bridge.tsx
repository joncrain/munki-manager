import { useAtom } from 'jotai'
import { useTheme } from 'next-themes'
import { useLayoutEffect } from 'react'
import { themePreferenceAtom } from '@/lib/atoms/ui'

/**
 * Applies the Jotai-persisted theme to next-themes. next-themes uses a separate `storageKey` so
 * Jotai remains the only writer to `theme` in localStorage.
 */
export function ThemeJotaiBridge() {
  const [theme] = useAtom(themePreferenceAtom)
  const { setTheme } = useTheme()

  useLayoutEffect(() => {
    setTheme(theme)
  }, [setTheme, theme])

  return null
}
