import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { AuditDetailDialog } from '@/components/audit/audit-detail-dialog'
import { auditLogBaseColumns } from '@/components/audit/audit-log-columns'
import { useAuth } from '@/components/auth-provider'
import { DataTable } from '@/components/data-table'
import { type AuditLogRead, api } from '@/lib/api'
import { PAGE_KEYS } from '@/lib/page-keys'
import { cn } from '@/lib/utils'

export function EntityAuditTrail({
  entityType,
  entityId,
  className,
}: {
  entityType: string
  entityId: string
  className?: string
}) {
  const { canRead } = useAuth()
  const canViewDetails = canRead(PAGE_KEYS.adminAudit)
  const [selectedEntry, setSelectedEntry] = useState<AuditLogRead | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['audit', entityType, entityId],
    queryFn: () => api.get<AuditLogRead[]>(`/audit/${entityType}/${entityId}`),
    enabled: Boolean(entityId),
  })

  const rows = useMemo(() => data ?? [], [data])

  if (!isLoading && rows.length === 0) {
    return (
      <p className={cn('text-sm text-muted-foreground', className)}>
        No audit history
      </p>
    )
  }

  return (
    <div className={cn('flex min-h-[240px] flex-col gap-2', className)}>
      {canViewDetails ? (
        <p className="text-xs text-muted-foreground">
          Click a row to view change details.
        </p>
      ) : null}
      <DataTable
        columns={auditLogBaseColumns}
        data={rows}
        isLoading={isLoading}
        hideColumnPicker
        getRowId={(row) => row.id}
        onRowClick={canViewDetails ? (row) => setSelectedEntry(row) : undefined}
        rowClassName={
          canViewDetails ? 'cursor-pointer hover:bg-muted/50' : undefined
        }
      />
      {canViewDetails ? (
        <AuditDetailDialog
          entry={selectedEntry}
          open={selectedEntry !== null}
          onOpenChange={(open) => {
            if (!open) setSelectedEntry(null)
          }}
        />
      ) : null}
    </div>
  )
}
