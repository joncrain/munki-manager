import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Provider as JotaiProvider } from 'jotai'
import { ThemeProvider } from 'next-themes'
import { NuqsAdapter } from 'nuqs/adapters/react-router'
import { useState } from 'react'
import { AuthProvider } from '@/components/auth-provider'
import { ColorPaletteProvider } from '@/components/color-palette-provider'
import { ThemeJotaiBridge } from '@/components/theme-jotai-bridge'
import { Toaster } from '@/components/ui/sonner'
import { TooltipProvider } from '@/components/ui/tooltip'
import { THEME_INTERNAL_STORAGE_KEY } from '@/lib/atoms/ui'

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30 * 1000,
            refetchOnWindowFocus: false,
          },
        },
      }),
  )

  return (
    <JotaiProvider>
      <ThemeProvider
        attribute="class"
        defaultTheme="system"
        enableSystem
        storageKey={THEME_INTERNAL_STORAGE_KEY}
      >
        <ThemeJotaiBridge />
        <ColorPaletteProvider>
          <NuqsAdapter>
            <QueryClientProvider client={queryClient}>
              <AuthProvider>
                <TooltipProvider>
                  {children}
                  <Toaster richColors />
                </TooltipProvider>
              </AuthProvider>
            </QueryClientProvider>
          </NuqsAdapter>
        </ColorPaletteProvider>
      </ThemeProvider>
    </JotaiProvider>
  )
}
