import { useQueryClient } from '@tanstack/react-query'
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react'
import { useNavigate } from 'react-router-dom'

import {
  redirectToLoginForExpiredAuth,
  registerAuthRedirectCacheBuster,
} from '@/lib/auth-redirect'
import { PAGE_KEYS } from '@/lib/page-keys'
import { publicApiBaseUrl } from '@/lib/public-api-base'

const API_BASE = publicApiBaseUrl()

export type AuthUser = {
  id: string
  email: string
  is_active: boolean
  is_superuser: boolean
  is_verified: boolean
  display_name?: string | null
  role?: string
  updated_at?: string | null
  has_avatar?: boolean
}

export type MePayload = {
  user: AuthUser
  permissions: Record<string, string>
  auth_mode: string
  is_demo?: boolean
}

const AuthContext = createContext<{
  me: MePayload | null
  /** ``me.auth_mode`` if logged in, else ``GET /auth/config`` (no separate env). */
  authMode: string | null
  /** From ``GET /auth/config`` — ``POST /auth/register`` allowed when true. */
  registrationOpen: boolean
  /** Read-only demo session from ``POST /auth/demo``. */
  isDemo: boolean
  loading: boolean
  refresh: () => Promise<void>
  logout: () => void
  canRead: (pageKey: string) => boolean
  canWrite: (pageKey: string) => boolean
} | null>(null)

function authHeaders(): HeadersInit {
  const token =
    typeof window !== 'undefined' ? localStorage.getItem('token') : null
  const h: Record<string, string> = {}
  if (token) h.Authorization = `Bearer ${token}`
  return h
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<MePayload | null>(null)
  const [serverAuthMode, setServerAuthMode] = useState<string | null>(null)
  const [registrationOpen, setRegistrationOpen] = useState(false)
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  // Hand the QueryClient to the (non-React) auth-redirect helper so it can
  // clear cached data the instant we detect an expired token. Without this
  // a slow-cold-DB 401 can fire after the user already started clicking
  // around on stale-but-valid-looking cached responses.
  useEffect(() => {
    registerAuthRedirectCacheBuster(queryClient)
  }, [queryClient])

  const authMode = useMemo(
    () => me?.auth_mode ?? serverAuthMode ?? null,
    [me, serverAuthMode],
  )

  const isDemo = Boolean(me?.is_demo)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      let modeFromConfig: string | null = null
      try {
        const cfgRes = await fetch(`${API_BASE}/api/v1/auth/config`)
        if (cfgRes.ok) {
          const cfg = (await cfgRes.json()) as {
            auth_mode: string
            registration_open?: boolean
          }
          modeFromConfig = cfg.auth_mode
          setServerAuthMode(cfg.auth_mode)
          setRegistrationOpen(Boolean(cfg.registration_open))
        }
        // On HTTP/network errors, keep last known serverAuthMode so RBAC + nav
        // don't briefly fall back to anonymous-jwt (empty sidebar / flash).
      } catch {
        /* preserve serverAuthMode */
      }

      // Fast-path: when auth is required, no token in localStorage means we
      // already know /auth/me will 401. Bounce immediately rather than
      // waiting on the network round-trip — on a cold ACA database this
      // saves the user 5-10 seconds of clicking through stale cache.
      const token =
        typeof window !== 'undefined' ? localStorage.getItem('token') : null
      if (modeFromConfig && modeFromConfig !== 'disabled' && !token) {
        setMe(null)
        redirectToLoginForExpiredAuth()
        return
      }

      const res = await fetch(`${API_BASE}/api/v1/auth/me`, {
        headers: { ...authHeaders() },
      })
      if (res.status === 401) {
        setMe(null)
        // Skip the redirect when the server is in disabled-auth mode (it
        // shouldn't 401 in that mode, but defend against drift). Otherwise
        // delegate to the shared helper so the path-allowlist + coalescing
        // matches the rest of the app — this also clears the React Query
        // cache before navigating so stale data doesn't render mid-redirect.
        if (modeFromConfig !== 'disabled') {
          redirectToLoginForExpiredAuth()
        }
        return
      }
      if (!res.ok) {
        setMe(null)
        return
      }
      const data = (await res.json()) as MePayload
      setMe(data)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const logout = useCallback(() => {
    localStorage.removeItem('token')
    // Same reasoning as the 401 path: drop cached data so a brief render
    // between setMe(null) and navigate() can't leak the previous user's
    // dashboard / lists. cancelQueries() returns a Promise we don't await
    // — navigation will tear down components either way, but a stray
    // late-resolving query before unmount would otherwise repopulate the
    // store on top of the cleared one.
    void queryClient.cancelQueries()
    queryClient.clear()
    setMe(null)
    navigate('/login')
  }, [navigate, queryClient])

  const canRead = useCallback(
    (pageKey: string) => {
      if (authMode === 'disabled') {
        return true
      }
      // Unknown mode (config not loaded yet or transient failure): don't strip nav.
      if (authMode === null) {
        return true
      }
      if (me?.user.is_superuser) {
        return true
      }
      const p = me?.permissions[pageKey]
      if (p === 'read' || p === 'write') {
        return true
      }
      if (
        me &&
        Object.keys(me.permissions).length === 0 &&
        pageKey !== PAGE_KEYS.adminAccess &&
        pageKey !== PAGE_KEYS.adminAiInsights
      ) {
        return true
      }
      return false
    },
    [me, authMode],
  )

  const canWrite = useCallback(
    (pageKey: string) => {
      if (authMode === 'disabled') {
        return true
      }
      if (authMode === null) {
        return true
      }
      if (me?.user.is_superuser) {
        return true
      }
      return me?.permissions[pageKey] === 'write'
    },
    [me, authMode],
  )

  const value = useMemo(
    () => ({
      me,
      authMode,
      registrationOpen,
      isDemo,
      loading,
      refresh,
      logout,
      canRead,
      canWrite,
    }),
    [
      me,
      authMode,
      registrationOpen,
      isDemo,
      loading,
      refresh,
      logout,
      canRead,
      canWrite,
    ],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) {
    throw new Error('useAuth must be used within AuthProvider')
  }
  return ctx
}
