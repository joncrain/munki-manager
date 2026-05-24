/** Tab / history title: `Group | Page | Detail` (sidebar section first). */
export function documentTitle(
  ...parts: (string | null | undefined | false)[]
): string {
  const segments = parts
    .map((p) => (p == null || p === false ? '' : String(p).trim()))
    .filter(Boolean)
  return segments.length > 0 ? segments.join(' | ') : '—'
}
