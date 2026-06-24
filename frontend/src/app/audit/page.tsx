import { ClipboardList } from 'lucide-react'
import { parseAsString, useQueryState } from 'nuqs'
import { useState } from 'react'
import { AuditDetailDialog } from '@/components/audit/audit-detail-dialog'
import { auditLogAdminColumns } from '@/components/audit/audit-log-columns'
import { DataTable } from '@/components/data-table'
import { FilterSheetField, PageFilters } from '@/components/page-filters'
import { PageHeading } from '@/components/page-heading'
import { SearchInput } from '@/components/search-input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useDocumentTitle } from '@/hooks/use-document-title'
import { usePaginatedListQuery } from '@/hooks/use-paginated-list-query'
import type { AuditLogRead } from '@/lib/api'

const ACTION_OPTIONS = [
  'approve',
  'approve_trust',
  'create',
  'create_override',
  'delete',
  'import',
  'import_override',
  'insights_query',
  'makecatalogs',
  'promote',
  'reject',
  'reject_trust',
  'repo_update',
  'scheduled_run',
  'shard_complete',
  'shard_override',
  'shard_pause',
  'shard_start',
  'software.direct_upload',
  'trigger_run',
  'update',
  'update_trust',
  'verify_trust',
  'verify_trust_before_run',
]

const ENTITY_OPTIONS = [
  'autopkg_recipe',
  'autopkg_run',
  'autopkg_run_result',
  'autopkg_system',
  'catalog',
  'insights',
  'manifest',
  'pkg_info',
  'pkginfo',
  'promotion_channel',
  'repository',
  'workflow_preferences',
]

export default function AuditPage() {
  useDocumentTitle('Admin', 'Audit Log')
  const [selectedEntry, setSelectedEntry] = useState<AuditLogRead | null>(null)
  const [action, setAction] = useQueryState(
    'action',
    parseAsString.withDefault(''),
  )
  const [entityType, setEntityType] = useQueryState(
    'entityType',
    parseAsString.withDefault(''),
  )
  const [search, setSearch] = useQueryState(
    'search',
    parseAsString.withDefault(''),
  )

  const {
    page,
    setPage,
    pageSize,
    resetPage,
    onPageSizeChange,
    data,
    isLoading,
  } = usePaginatedListQuery<AuditLogRead>({
    queryKeyPrefix: ['audit'],
    path: '/audit',
    filterKey: [action, entityType, search],
    appendSearchParams: (params) => {
      if (action) params.set('action', action)
      if (entityType) params.set('entity_type', entityType)
      const trimmedSearch = search.trim()
      if (trimmedSearch) params.set('search', trimmedSearch)
    },
  })

  const hasSheetFilters = Boolean(action || entityType)
  const activeFilterCount = [action, entityType].filter(Boolean).length
  const activeFilters = [
    ...(action
      ? [
          {
            id: 'action',
            label: `Action: ${action}`,
            onRemove: () => {
              void setAction(null)
              resetPage()
            },
          },
        ]
      : []),
    ...(entityType
      ? [
          {
            id: 'entityType',
            label: `Entity: ${entityType}`,
            onRemove: () => {
              void setEntityType(null)
              resetPage()
            },
          },
        ]
      : []),
  ]

  return (
    <div className="flex h-[calc(100vh-3rem)] flex-col gap-4">
      <PageHeading icon={ClipboardList} accent="audit" title="Audit Log" />

      <PageFilters
        isFiltered={hasSheetFilters}
        activeFilterCount={activeFilterCount}
        activeFilters={activeFilters}
        sheetDescription="Refine audit log entries."
        onClear={() => {
          setAction(null)
          setEntityType(null)
          resetPage()
        }}
        search={
          <SearchInput
            placeholder="Search entity or user..."
            value={search}
            onChange={(e) => {
              setSearch(e.target.value)
              resetPage()
            }}
            onClear={() => {
              setSearch('')
              resetPage()
            }}
          />
        }
      >
        <FilterSheetField
          label="Action"
          hasValue={Boolean(action)}
          onClear={() => {
            setAction(null)
            resetPage()
          }}
        >
          <Select
            value={action || '_all'}
            onValueChange={(v) => {
              setAction(v === '_all' ? null : v)
              resetPage()
            }}
          >
            <SelectTrigger className="w-full">
              <SelectValue placeholder="Action" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="_all">All Actions</SelectItem>
              {ACTION_OPTIONS.map((a) => (
                <SelectItem key={a} value={a}>
                  {a}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </FilterSheetField>

        <FilterSheetField
          label="Entity type"
          hasValue={Boolean(entityType)}
          onClear={() => {
            setEntityType(null)
            resetPage()
          }}
        >
          <Select
            value={entityType || '_all'}
            onValueChange={(v) => {
              setEntityType(v === '_all' ? null : v)
              resetPage()
            }}
          >
            <SelectTrigger className="w-full">
              <SelectValue placeholder="Entity Type" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="_all">All Entities</SelectItem>
              {ENTITY_OPTIONS.map((e) => (
                <SelectItem key={e} value={e}>
                  {e}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </FilterSheetField>
      </PageFilters>

      <p className="text-xs text-muted-foreground">
        Click a row to view change details.
      </p>

      <div className="flex-1 min-h-0">
        <DataTable
          columns={auditLogAdminColumns}
          data={data?.items ?? []}
          pageCount={data?.total_pages ?? 1}
          page={page}
          pageSize={pageSize}
          total={data?.total}
          onPageChange={setPage}
          onPageSizeChange={onPageSizeChange}
          isLoading={isLoading}
          getRowId={(row) => row.id}
          onRowClick={(row) => setSelectedEntry(row)}
          rowClassName="cursor-pointer hover:bg-muted/50"
        />
      </div>

      <AuditDetailDialog
        entry={selectedEntry}
        open={selectedEntry !== null}
        onOpenChange={(open) => {
          if (!open) setSelectedEntry(null)
        }}
      />
    </div>
  )
}
