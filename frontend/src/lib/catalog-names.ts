export function catalogNameSetsEqual(a: string[], b: string[]): boolean {
  if (a.length !== b.length) {
    return false
  }
  const sa = [...a]
    .map((s) => s.trim())
    .filter(Boolean)
    .sort()
  const sb = [...b]
    .map((s) => s.trim())
    .filter(Boolean)
    .sort()
  for (let i = 0; i < sa.length; i++) {
    if (sa[i] !== sb[i]) {
      return false
    }
  }
  return true
}
