import type { ColumnDef } from '@tanstack/react-table'
import { Badge } from '@/components/ui/badge'
import type { AuditLogRead } from '@/lib/api'
import { auditActionVariant } from '@/lib/audit-display'
import { formatDateTime } from '@/lib/format'

export const auditLogBaseColumns: ColumnDef<AuditLogRead>[] = [
  {
    accessorKey: 'created_at',
    header: 'Time',
    cell: ({ row }) => (
      <span suppressHydrationWarning className="text-sm whitespace-nowrap">
        {formatDateTime(row.original.created_at)}
      </span>
    ),
  },
  {
    accessorKey: 'action',
    header: 'Action',
    cell: ({ row }) => (
      <Badge variant={auditActionVariant(row.original.action)}>
        {row.original.action}
      </Badge>
    ),
  },
  {
    accessorKey: 'user_email',
    header: 'User',
    cell: ({ row }) => (
      <span className="text-sm">{row.original.user_email || 'system'}</span>
    ),
  },
  {
    accessorKey: 'notes',
    header: 'Notes',
    cell: ({ row }) => (
      <span className="line-clamp-2 text-sm text-muted-foreground">
        {row.original.notes || '—'}
      </span>
    ),
  },
]

export const auditLogAdminColumns: ColumnDef<AuditLogRead>[] = [
  ...auditLogBaseColumns.slice(0, 2),
  {
    accessorKey: 'entity_type',
    header: 'Entity Type',
    cell: ({ row }) => (
      <Badge variant="outline">{row.original.entity_type}</Badge>
    ),
  },
  {
    accessorKey: 'entity_name',
    header: 'Entity',
    cell: ({ row }) => (
      <span className="truncate">
        {row.original.entity_name || row.original.entity_id}
      </span>
    ),
  },
  ...auditLogBaseColumns.slice(2),
]
