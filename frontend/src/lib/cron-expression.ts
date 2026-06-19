import cronstrue from 'cronstrue'

/** Human-readable description of a five-field cron expression. */
export function formatCronExpression(expr: string): string {
  const trimmed = expr.trim()
  if (!trimmed) return '—'
  try {
    return cronstrue.toString(trimmed, { throwExceptionOnParseError: true })
  } catch {
    return trimmed
  }
}
