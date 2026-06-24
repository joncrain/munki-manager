import type { ColumnDef } from '@tanstack/react-table'
import { Link } from 'react-router-dom'
import { VersionWithLatestBadge } from '@/components/latest-version-badge'
import { Badge } from '@/components/ui/badge'
import type { ClientInstallReportListItem } from '@/lib/api'
import {
  formatDateTime,
  formatInstallReason,
  installReportStatusVariant,
} from '@/lib/format'
import { looseVersionSortingFn } from '@/lib/loose-version'

export function softwareInstallReportColumns(
  latestVersion: string | undefined,
): ColumnDef<ClientInstallReportListItem>[] {
  return [
    {
      accessorKey: 'created_at',
      header: 'Reported',
      cell: ({ row }) => (
        <span suppressHydrationWarning className="text-sm">
          {formatDateTime(row.original.created_at)}
        </span>
      ),
    },
    {
      accessorKey: 'item_version',
      header: 'Version',
      sortingFn: looseVersionSortingFn,
      cell: ({ row }) => (
        <VersionWithLatestBadge
          version={row.original.item_version}
          isLatest={
            !!row.original.item_version &&
            !!latestVersion &&
            row.original.item_version === latestVersion
          }
        />
      ),
    },
    {
      accessorKey: 'status',
      header: 'Status',
      cell: ({ row }) => (
        <Badge variant={installReportStatusVariant(row.original.status)}>
          {row.original.status}
        </Badge>
      ),
    },
    {
      accessorKey: 'install_reason',
      header: 'Reason',
      cell: ({ row }) => (
        <span className="text-sm text-muted-foreground">
          {formatInstallReason(row.original.install_reason)}
        </span>
      ),
    },
    {
      accessorKey: 'hostname',
      header: 'Device',
      cell: ({ row }) => (
        <Link
          to={`/reporting/devices/${row.original.machine_id}`}
          className="text-primary underline-offset-4 hover:underline"
        >
          {row.original.hostname || row.original.serial_number || '—'}
        </Link>
      ),
    },
    {
      accessorKey: 'install_date',
      header: 'Install time',
      cell: ({ row }) =>
        row.original.install_date ? (
          <span suppressHydrationWarning className="text-sm">
            {formatDateTime(row.original.install_date)}
          </span>
        ) : (
          '—'
        ),
    },
    {
      accessorKey: 'error_message',
      header: 'Note',
      cell: ({ row }) => (
        <span className="line-clamp-2 max-w-[240px] text-sm text-muted-foreground">
          {row.original.error_message || '—'}
        </span>
      ),
    },
  ]
}
