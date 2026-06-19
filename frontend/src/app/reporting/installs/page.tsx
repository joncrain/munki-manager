import { useQuery } from '@tanstack/react-query'
import type { ColumnDef } from '@tanstack/react-table'
import { ListChecks, X } from 'lucide-react'
import { parseAsInteger, parseAsString, useQueryState } from 'nuqs'
import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { DataTable } from '@/components/data-table'
import { VersionWithLatestBadge } from '@/components/latest-version-badge'
import { PageHeading } from '@/components/page-heading'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useDocumentTitle } from '@/hooks/use-document-title'
import {
  installReportLinkKey,
  usePkginfoLinksForInstallReports,
} from '@/hooks/use-pkginfo-display-labels'
import {
  api,
  type ClientInstallReportListItem,
  type PaginatedResponse,
} from '@/lib/api'
import { formatDateTime, formatInstallReason } from '@/lib/format'
import { looseVersionSortingFn } from '@/lib/loose-version'

const STATUS_OPTIONS = [
  'installed',
  'failed',
  'removed',
  'removal_failed',
  'unknown',
]

function statusVariant(status: string) {
  switch (status) {
    case 'installed':
      return 'default' as const
    case 'failed':
    case 'removal_failed':
      return 'destructive' as const
    case 'removed':
      return 'secondary' as const
    default:
      return 'outline' as const
  }
}

function makeColumns(
  links:
    | Record<
        string,
        { displayName: string; pkginfoId: string | null; isLatest: boolean }
      >
    | undefined,
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
      accessorKey: 'item_name',
      header: 'Item',
      cell: ({ row }) => {
        const { item_name, item_version } = row.original
        if (!item_name) return '—'
        const link = links?.[installReportLinkKey(item_name, item_version)]
        const label = link?.displayName ?? item_name
        if (link?.pkginfoId) {
          return (
            <Link
              to={`/software/${link.pkginfoId}`}
              className="font-medium text-primary underline-offset-4 hover:underline"
            >
              {label}
            </Link>
          )
        }
        return <span className="font-medium">{label}</span>
      },
    },
    {
      accessorKey: 'item_version',
      header: 'Version',
      sortingFn: looseVersionSortingFn,
      cell: ({ row }) => {
        const { item_name, item_version } = row.original
        const link = item_name
          ? links?.[installReportLinkKey(item_name, item_version)]
          : undefined
        return (
          <VersionWithLatestBadge
            version={item_version}
            isLatest={link?.isLatest}
          />
        )
      },
    },
    {
      accessorKey: 'status',
      header: 'Status',
      cell: ({ row }) => (
        <Badge variant={statusVariant(row.original.status)}>
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
      accessorKey: 'serial_number',
      header: 'Serial',
      cell: ({ row }) => (
        <span className="font-mono text-xs text-muted-foreground">
          {row.original.serial_number || '—'}
        </span>
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

export default function ReportingInstallsPage() {
  useDocumentTitle('Reporting', 'Installs')
  const [page, setPage] = useQueryState('page', parseAsInteger.withDefault(1))
  const [pageSize, setPageSize] = useQueryState(
    'pageSize',
    parseAsInteger.withDefault(50),
  )
  const [search, setSearch] = useQueryState('q', parseAsString.withDefault(''))
  const [status, setStatus] = useQueryState(
    'status',
    parseAsString.withDefault(''),
  )

  const { data, isLoading } = useQuery({
    queryKey: ['reports-installs', page, pageSize, search, status],
    queryFn: () => {
      const params = new URLSearchParams()
      params.set('page', String(page))
      params.set('page_size', String(pageSize))
      if (search.trim()) params.set('search', search.trim())
      if (status.trim()) params.set('status', status.trim())
      return api.get<PaginatedResponse<ClientInstallReportListItem>>(
        `/reports/installs?${params.toString()}`,
      )
    },
  })

  const rows = data?.items ?? []
  const { data: pkginfoLinks } = usePkginfoLinksForInstallReports(rows)
  const columns = useMemo(() => makeColumns(pkginfoLinks), [pkginfoLinks])

  const hasFilters = Boolean(search.trim() || status.trim())

  return (
    <div className="flex h-[calc(100vh-3rem)] flex-col gap-4">
      <div>
        <PageHeading icon={ListChecks} accent="reporting" title="Installs" />
        <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
          Historical install and removal events from client check-ins.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Input
          placeholder="Search item, hostname, or serial…"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value || null)
            setPage(1)
          }}
          className="max-w-sm"
          aria-label="Search installs"
        />
        <Select
          value={status || '_all'}
          onValueChange={(v) => {
            setStatus(v === '_all' ? null : v)
            setPage(1)
          }}
        >
          <SelectTrigger className="w-[180px]">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="_all">All statuses</SelectItem>
            {STATUS_OPTIONS.map((s) => (
              <SelectItem key={s} value={s}>
                {s}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {hasFilters && (
          <Button
            variant="ghost"
            size="sm"
            aria-label="Clear filters"
            onClick={() => {
              setSearch(null)
              setStatus(null)
              setPage(1)
            }}
          >
            <X className="h-4 w-4" />
            Clear
          </Button>
        )}
      </div>

      <div className="min-h-0 flex-1">
        <DataTable
          columns={columns}
          data={rows}
          pageCount={data?.total_pages ?? 1}
          page={page}
          pageSize={pageSize}
          total={data?.total}
          onPageChange={setPage}
          onPageSizeChange={(size) => {
            setPageSize(size)
            setPage(1)
          }}
          isLoading={isLoading}
        />
      </div>
    </div>
  )
}
