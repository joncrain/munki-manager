import { useEffect } from 'react'
import { Outlet } from 'react-router-dom'
import './app/globals.css'
import { AppShell } from '@/components/app-shell'
import { Providers } from '@/components/providers'
import { CHUNK_RELOAD_KEY } from '@/components/route-error-boundary'

export default function RootLayout() {
  // Reaching RootLayout means the SPA shell rendered without a chunk-load
  // failure, so clear the one-shot auto-reload guard. A *later* failure in
  // the same session (e.g. another deploy) will then get its own recovery
  // attempt instead of going straight to the manual-reload card.
  useEffect(() => {
    sessionStorage.removeItem(CHUNK_RELOAD_KEY)
  }, [])

  return (
    <Providers>
      <AppShell>
        <Outlet />
      </AppShell>
    </Providers>
  )
}
