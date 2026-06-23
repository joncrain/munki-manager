import { Link } from 'react-router-dom'

import { useAuth } from '@/components/auth-provider'

export function DemoBanner() {
  const { isDemo } = useAuth()

  if (!isDemo) {
    return null
  }

  return (
    <div className="mb-4 rounded-md border border-amber-500/40 bg-amber-500/10 px-4 py-2 text-sm text-amber-950 dark:text-amber-100">
      Read-only demo —{' '}
      <Link to="/login" className="font-medium underline underline-offset-2">
        Sign in for full access
      </Link>
    </div>
  )
}
