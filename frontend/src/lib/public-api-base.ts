/**
 * Normalizes ``VITE_PUBLIC_API_URL`` for browser ``fetch`` calls that append ``/api/v1``.
 *
 * Accepts either ``http://host:8000`` or the misconfigured ``http://host:8000/api/v1``
 * so we never request ``/api/v1/api/v1/...`` (404 Not Found).
 */
export function publicApiBaseUrl(): string {
  const raw = import.meta.env.VITE_PUBLIC_API_URL ?? ''
  let s = raw.trim()
  if (!s) return ''
  s = s.replace(/\/+$/, '')
  if (s.toLowerCase().endsWith('/api/v1')) {
    s = s.slice(0, -'/api/v1'.length)
    s = s.replace(/\/+$/, '')
  }
  return s
}
