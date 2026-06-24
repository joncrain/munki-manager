import { useQuery } from '@tanstack/react-query'
import type { ColumnDef } from '@tanstack/react-table'
import { MonitorSmartphone } from 'lucide-react'
import { parseAsString, useQueryState } from 'nuqs'
import { useMemo } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { DataTable } from '@/components/data-table'
import { FilterBadge } from '@/components/filter-badge'
import { FilterSheetField, PageFilters } from '@/components/page-filters'
import { PageHeading } from '@/components/page-heading'
import {
  CheckinFilterControl,
  checkinFilterActiveCount,
  checkinFilterIsActive,
} from '@/components/reporting/checkin-filter-control'
import { SearchInput } from '@/components/search-input'
import { useDocumentTitle } from '@/hooks/use-document-title'
import { usePaginatedListQuery } from '@/hooks/use-paginated-list-query'
import { api, type ClientMachineSummary, type ManifestRead } from '@/lib/api'
import { formatDateTime } from '@/lib/format'
import {
  checkinFilterApiParams,
  checkinFilterLabel,
  parseCheckinFilter,
} from '@/lib/reporting-device-filters'

function makeColumns(
  manifestIdByName: Map<string, string>,
  filters: {
    onNeverCheckinFilter: () => void
    onInstallRowsFilter: (hostname: string, serial: string) => void
  },
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
          <FilterBadge
            variant="outline"
            className="font-normal text-muted-foreground"
            onFilter={filters.onNeverCheckinFilter}
            ariaLabel="Filter to devices that never checked in"
          >
            Never
          </FilterBadge>
        ),
    },
    {
      accessorKey: 'install_report_count',
      header: 'Install rows',
      cell: ({ row }) => {
        const { install_report_count, hostname, serial_number } = row.original
        const label = String(install_report_count)
        const deviceLabel = hostname || serial_number || 'this device'
        return (
          <FilterBadge
            variant="outline"
            onFilter={() =>
              filters.onInstallRowsFilter(hostname ?? '', serial_number ?? '')
            }
            ariaLabel={`View install reports for ${deviceLabel}`}
          >
            {label}
          </FilterBadge>
        )
      },
    },
  ]
}

export default function ReportingPage() {
  useDocumentTitle('Reporting', 'Devices')
  const navigate = useNavigate()
  const [search, setSearch] = useQueryState('q', parseAsString.withDefault(''))
  const [checkinFilterRaw, setCheckinFilter] = useQueryState(
    'stale',
    parseAsString.withDefault(''),
  )
  const checkinFilter = parseCheckinFilter(checkinFilterRaw)

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
    filterKey: [search, checkinFilterRaw],
    appendSearchParams: (params) => {
      if (search.trim()) params.set('search', search.trim())
      for (const [key, value] of checkinFilterApiParams(checkinFilter)) {
        params.set(key, value)
      }
    },
  })

  const columns = useMemo(
    () =>
      makeColumns(manifestIdByName, {
        onNeverCheckinFilter: () => {
          setCheckinFilter('never')
          resetPage()
        },
        onInstallRowsFilter: (hostname, serial) => {
          const q = hostname.trim() || serial.trim()
          if (!q) return
          navigate(`/reporting/installs?q=${encodeURIComponent(q)}`)
        },
      }),
    [manifestIdByName, navigate, resetPage, setCheckinFilter],
  )

  const hasSheetFilters = checkinFilterIsActive(checkinFilterRaw)
  const activeFilters = hasSheetFilters
    ? [
        {
          id: 'checkin',
          label: checkinFilterLabel(checkinFilter),
          onRemove: () => {
            void setCheckinFilter(null)
            resetPage()
          },
        },
      ]
    : []

  return (
    <div className="flex h-[calc(100vh-3rem)] flex-col gap-4">
      <div>
        <PageHeading
          icon={MonitorSmartphone}
          accent="reporting"
          title="Devices"
        />
      </div>

      <PageFilters
        isFiltered={hasSheetFilters}
        activeFilterCount={checkinFilterActiveCount(checkinFilterRaw)}
        activeFilters={activeFilters}
        sheetDescription="Refine the device list."
        onClear={() => {
          setCheckinFilter(null)
          resetPage()
        }}
        search={
          <SearchInput
            placeholder="Search hostname or serial…"
            value={search}
            aria-label="Search devices"
            onChange={(e) => {
              setSearch(e.target.value || null)
              resetPage()
            }}
            onClear={() => {
              setSearch(null)
              resetPage()
            }}
          />
        }
      >
        <FilterSheetField
          label="Check-in activity"
          hasValue={checkinFilterIsActive(parseCheckinFilter(checkinFilterRaw))}
          onClear={() => {
            setCheckinFilter(null)
            resetPage()
          }}
        >
          <CheckinFilterControl
            value={checkinFilterRaw}
            onChange={(next) => {
              setCheckinFilter(next)
            }}
            onApply={resetPage}
          />
        </FilterSheetField>
      </PageFilters>

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
