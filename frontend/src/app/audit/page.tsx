import { useQuery } from '@tanstack/react-query'
import { ClipboardList, Search, X } from 'lucide-react'
import { parseAsInteger, parseAsString, useQueryState } from 'nuqs'
import { useState } from 'react'
import { AuditDetailDialog } from '@/components/audit/audit-detail-dialog'
import { auditLogAdminColumns } from '@/components/audit/audit-log-columns'
import { DataTable } from '@/components/data-table'
import { PageHeading } from '@/components/page-heading'
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
import { type AuditLogRead, api, type PaginatedResponse } from '@/lib/api'

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
  const [page, setPage] = useQueryState('page', parseAsInteger.withDefault(1))
  const [pageSize, setPageSize] = useQueryState(
    'pageSize',
    parseAsInteger.withDefault(50),
  )
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

  const { data, isLoading } = useQuery({
    queryKey: ['audit', page, pageSize, action, entityType, search],
    queryFn: () => {
      const params = new URLSearchParams()
      params.set('page', String(page))
      params.set('page_size', String(pageSize))
      if (action) params.set('action', action)
      if (entityType) params.set('entity_type', entityType)
      const trimmedSearch = search.trim()
      if (trimmedSearch) params.set('search', trimmedSearch)
      return api.get<PaginatedResponse<AuditLogRead>>(
        `/audit?${params.toString()}`,
      )
    },
  })

  const hasFilters = action || entityType || search

  return (
    <div className="flex h-[calc(100vh-3rem)] flex-col gap-4">
      <PageHeading icon={ClipboardList} accent="audit" title="Audit Log" />

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative max-w-sm flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search entity or user..."
            value={search}
            onChange={(e) => {
              setSearch(e.target.value)
              setPage(1)
            }}
            className="pl-9"
          />
        </div>

        <Select
          value={action || '_all'}
          onValueChange={(v) => {
            setAction(v === '_all' ? null : v)
            setPage(1)
          }}
        >
          <SelectTrigger className="w-[140px]">
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

        <Select
          value={entityType || '_all'}
          onValueChange={(v) => {
            setEntityType(v === '_all' ? null : v)
            setPage(1)
          }}
        >
          <SelectTrigger className="w-[160px]">
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

        {hasFilters && (
          <Button
            variant="ghost"
            size="sm"
            aria-label="Clear filters"
            onClick={() => {
              setAction(null)
              setEntityType(null)
              setSearch(null)
              setPage(1)
            }}
          >
            <X className="h-4 w-4" />
            Clear
          </Button>
        )}
      </div>

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
          onPageSizeChange={(size) => {
            setPageSize(size)
            setPage(1)
          }}
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
