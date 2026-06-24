import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from 'react-router-dom'
import { migrateAutopkgRunnerLocalStorageFromRebrand } from '@/lib/autopkg-run'
import { router } from '@/router'

migrateAutopkgRunnerLocalStorageFromRebrand()

const rootEl = document.getElementById('root')
if (!rootEl) {
  throw new Error('Root element #root not found')
}

createRoot(rootEl).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
)
