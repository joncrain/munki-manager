export const auditActionVariant = (action: string) => {
  switch (action) {
    case 'create':
      return 'default' as const
    case 'update':
      return 'secondary' as const
    case 'delete':
      return 'destructive' as const
    case 'promote':
    case 'approve':
      return 'default' as const
    case 'reject':
      return 'destructive' as const
    default:
      return 'outline' as const
  }
}

export function formatAuditJson(value: unknown): string {
  if (value == null) return '—'
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}
