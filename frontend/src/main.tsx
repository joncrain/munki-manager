import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from 'react-router-dom'
import { migrateAutopkgRunnerLocalStorageFromRebrand } from '@/lib/autopkg-run'
import { router } from '@/router'

migrateAutopkgRunnerLocalStorageFromRebrand()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
)
