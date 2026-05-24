/**
 * Centralized "auth expired" handler.
 *
 * The SPA used to surface 401s as in-page error states (a stale spinner,
 * a "Network error" toast, or — worst of all — a chunk-load error
 * masquerading as a backend cold start). When a JWT expires mid-session
 * the user really wants to be sent back to /login with their original
 * destination preserved.
 *
 * Called from:
 *   - {@link apiFetch} (every JSON API call)
 *   - the upload helpers in `lib/api.ts` (multipart / XHR)
 *   - {@link AuthProvider.refresh} on a 401 from /auth/me
 *
 * Implementation notes:
 *   - Uses `window.location.assign` rather than React Router's `navigate()`
 *     so it works from non-React modules and forces a clean tree (no stale
 *     React Query cache to flash).
 *   - Coalesces concurrent 401s via an in-memory flag — multiple parallel
 *     fetches that all expire at once should result in exactly one redirect.
 *   - No-ops on public routes (login / register / OIDC callback / device
 *     enrollment), so a 401 during the login attempt itself doesn't loop.
 */

const PUBLIC_PATH_PREFIXES = [
  '/login',
  '/register',
  '/auth/',
  '/enroll',
] as const

let redirectInFlight = false

export function isPublicAuthPath(pathname: string | null | undefined): boolean {
  if (!pathname) return false
  return PUBLIC_PATH_PREFIXES.some(
    (prefix) =>
      pathname === prefix ||
      pathname === prefix.replace(/\/$/, '') ||
      pathname.startsWith(prefix.endsWith('/') ? prefix : `${prefix}/`),
  )
}

/**
 * Send the browser to /login?next=<current-path>, preserving the
 * destination so the user lands back where they were after re-auth.
 *
 * Returns `true` when the redirect was issued (caller can stop further work),
 * `false` when it was suppressed (already on a public path, or another
 * redirect is in flight).
 */
export function redirectToLoginForExpiredAuth(): boolean {
  if (typeof window === 'undefined') return false
  if (redirectInFlight) return true

  const path = window.location.pathname
  if (isPublicAuthPath(path)) {
    return false
  }

  redirectInFlight = true
  try {
    localStorage.removeItem('token')
  } catch {
    /* private mode / storage disabled */
  }

  const next = `${window.location.pathname}${window.location.search}`
  const target = `/login?next=${encodeURIComponent(next || '/')}`
  window.location.assign(target)
  return true
}
