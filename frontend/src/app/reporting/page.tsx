import { useQuery } from '@tanstack/react-query'
import type { ColumnDef } from '@tanstack/react-table'
import { MonitorSmartphone } from 'lucide-react'
import { parseAsString, useQueryState } from 'nuqs'
import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { DataTable } from '@/components/data-table'
import { PageHeading } from '@/components/page-heading'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { useDocumentTitle } from '@/hooks/use-document-title'
import { usePaginatedListQuery } from '@/hooks/use-paginated-list-query'
import { api, type ClientMachineSummary, type ManifestRead } from '@/lib/api'
import { formatDateTime } from '@/lib/format'

function makeColumns(
  manifestIdByName: Map<string, string>,
): ColumnDef<ClientMachineSummary>[] {
  return [
    {
      accessorKey: 'hostname',
      header: 'Hostname',
      cell: ({ row }) => (
        <Link
          to={`/reporting/devices/${row.original.id}`}
          className="font-medium text-primary underline-offset-4 hover:underline"
        >
          {row.original.hostname || '—'}
        </Link>
      ),
    },
    {
      accessorKey: 'serial_number',
      header: 'Serial',
      cell: ({ row }) => (
        <span className="font-mono text-xs">{row.original.serial_number}</span>
      ),
    },
    {
      accessorKey: 'manifest_name',
      header: 'Manifest',
      cell: ({ row }) => {
        const name = row.original.manifest_name
        if (!name) return <span className="text-muted-foreground">—</span>
        const manifestId = manifestIdByName.get(name)
        if (manifestId) {
          return (
            <Link
              to={`/manifests/${manifestId}`}
              className="text-primary underline-offset-4 hover:underline"
            >
              {name}
            </Link>
          )
        }
        return <span>{name}</span>
      },
    },
    {
      accessorKey: 'munki_version',
      header: 'Munki',
      cell: ({ row }) => row.original.munki_version || '—',
    },
    {
      accessorKey: 'last_checkin_at',
      header: 'Last check-in',
      cell: ({ row }) =>
        row.original.last_checkin_at ? (
          <span suppressHydrationWarning className="text-sm">
            {formatDateTime(row.original.last_checkin_at)}
          </span>
        ) : (
          <span className="text-muted-foreground">Never</span>
        ),
    },
    {
      accessorKey: 'install_report_count',
      header: 'Install rows',
      cell: ({ row }) => (
        <Badge variant="outline">{row.original.install_report_count}</Badge>
      ),
    },
  ]
}

export default function ReportingPage() {
  useDocumentTitle('Reporting', 'Devices')
  const [search, setSearch] = useQueryState('q', parseAsString.withDefault(''))

  const { data: manifests } = useQuery({
    queryKey: ['manifests'],
    queryFn: () => api.get<ManifestRead[]>('/manifests'),
  })

  const manifestIdByName = useMemo(() => {
    const map = new Map<string, string>()
    for (const m of manifests ?? []) {
      map.set(m.name, m.id)
    }
    return map
  }, [manifests])

  const columns = useMemo(
    () => makeColumns(manifestIdByName),
    [manifestIdByName],
  )

  const {
    page,
    setPage,
    pageSize,
    resetPage,
    onPageSizeChange,
    data,
    isLoading,
  } = usePaginatedListQuery<ClientMachineSummary>({
    queryKeyPrefix: ['reports-machines'],
    path: '/reports/machines',
    filterKey: [search],
    appendSearchParams: (params) => {
      if (search.trim()) params.set('search', search.trim())
    },
  })

  return (
    <div className="flex h-[calc(100vh-3rem)] flex-col gap-6">
      <div>
        <PageHeading
          icon={MonitorSmartphone}
          accent="reporting"
          title="Devices"
        />
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Input
          placeholder="Search hostname or serial…"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value || null)
            resetPage()
          }}
          className="max-w-sm"
          aria-label="Search devices"
        />
      </div>

      <div className="min-h-0 flex-1">
        <DataTable
          columns={columns}
          data={data?.items ?? []}
          pageCount={data?.total_pages ?? 1}
          page={page}
          pageSize={pageSize}
          total={data?.total}
          onPageChange={setPage}
          onPageSizeChange={onPageSizeChange}
          isLoading={isLoading}
        />
      </div>
    </div>
  )
}
