import { Suspense, useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { AuthBrandHeader } from '@/components/auth-brand-header'
import { useAuth } from '@/components/auth-provider'
import { useDocumentTitle } from '@/hooks/use-document-title'

function AuthCallbackInner() {
  const { refresh } = useAuth()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    const token = searchParams.get('token')
    if (!token) {
      setErr('Missing token')
      return
    }
    let cancelled = false
    void (async () => {
      localStorage.setItem('token', token)
      await refresh()
      if (cancelled) return
      navigate('/', { replace: true })
    })()
    return () => {
      cancelled = true
    }
  }, [refresh, navigate, searchParams])

  if (err) {
    return (
      <div className="mx-auto max-w-sm space-y-6 p-6">
        <AuthBrandHeader />
        <p className="text-destructive">{err}</p>
      </div>
    )
  }
  return (
    <div className="mx-auto max-w-sm space-y-6 p-6">
      <AuthBrandHeader />
      <p className="text-center text-muted-foreground">Signing you in…</p>
    </div>
  )
}

export default function AuthCallbackPage() {
  useDocumentTitle('Sign in')
  return (
    <Suspense
      fallback={
        <div className="mx-auto max-w-sm space-y-6 p-6">
          <AuthBrandHeader />
          <p className="text-center text-muted-foreground">Loading…</p>
        </div>
      }
    >
      <AuthCallbackInner />
    </Suspense>
  )
}
