import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type {
  ColumnDef,
  RowSelectionState,
  VisibilityState,
} from '@tanstack/react-table'
import { useAtom } from 'jotai'
import { Package, Search, Tags, Trash2, Upload } from 'lucide-react'
import { useEffect, useId, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'
import { useAuth } from '@/components/auth-provider'
import { ColumnVisibilityMenu, DataTable } from '@/components/data-table'
import { DeploymentStatusBadge } from '@/components/deployment-status-badge'
import { VersionWithLatestBadge } from '@/components/latest-version-badge'
import { PageFilters } from '@/components/page-filters'
import { PageHeading } from '@/components/page-heading'
import { SoftwareIcon } from '@/components/software-icon'
import { SoftwareUploadDialog } from '@/components/software-upload-dialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { useDocumentTitle } from '@/hooks/use-document-title'
import {
  api,
  type CatalogRead,
  type PaginatedResponse,
  type PkgInfoBulkUpdateRequest,
  type PkgInfoBulkUpdateResult,
  type PkgInfoSummary,
} from '@/lib/api'
import { softwarePageListAtom } from '@/lib/atoms/software-page-list'
import { formatDate } from '@/lib/format'
import { munkiAccents } from '@/lib/munki-accents'
import { PAGE_KEYS } from '@/lib/page-keys'
import { cn } from '@/lib/utils'

const columns: ColumnDef<PkgInfoSummary>[] = [
  {
    accessorKey: 'display_name',
    header: 'Name',
    cell: ({ row }) => (
      <Link
        to={`/software/${row.original.id}`}
        className="flex items-center gap-3 font-medium hover:underline"
      >
        <SoftwareIcon
          name={row.original.name}
          displayName={row.original.display_name}
          size="sm"
        />
        <span className="truncate">
          {row.original.display_name || row.original.name}
        </span>
        {row.original.pending_metadata && (
          <Badge
            variant="outline"
            className="ml-1 shrink-0 border-amber-500 text-amber-600"
            title="Uploaded manually — finish entering version / receipts before promoting."
          >
            Manual
          </Badge>
        )}
      </Link>
    ),
    enableHiding: false,
  },
  {
    accessorKey: 'version',
    header: 'Version',
    cell: ({ row }) => (
      <VersionWithLatestBadge
        version={row.original.version}
        isLatest={row.original.is_latest}
      />
    ),
  },
  {
    accessorKey: 'category',
    header: 'Category',
    cell: ({ row }) =>
      row.original.category ? (
        <Badge variant="outline">{row.original.category}</Badge>
      ) : null,
  },
  {
    accessorKey: 'install_count',
    header: 'Installs',
    cell: ({ row }) => (
      <span className="tabular-nums text-sm">
        {row.original.install_count ?? 0}
      </span>
    ),
  },
  {
    accessorKey: 'failed_install_count',
    header: 'Failed',
    cell: ({ row }) => {
      const count = row.original.failed_install_count ?? 0
      return (
        <span
          className={cn(
            'tabular-nums text-sm',
            count > 0 && 'font-medium text-destructive',
          )}
        >
          {count}
        </span>
      )
    },
  },
  {
    accessorKey: 'developer',
    header: 'Developer',
    cell: ({ row }) => (
      <span className="truncate text-sm">{row.original.developer}</span>
    ),
  },
  {
    accessorKey: 'catalog_names',
    header: 'Catalogs',
    enableSorting: false,
    cell: ({ row }) => (
      <div className="flex gap-1">
        {row.original.catalog_names.map((c) => (
          <Badge key={c} variant="secondary">
            {c}
          </Badge>
        ))}
      </div>
    ),
  },
  {
    accessorKey: 'deployment_status',
    header: 'Deployment',
    enableSorting: false,
    cell: ({ row }) => (
      <DeploymentStatusBadge
        deploymentStatus={row.original.deployment_status ?? 'not_in_production'}
        shardPercent={row.original.shard_percent ?? null}
        isFirstProductionDeploy={row.original.is_first_production_deploy}
        inManifest={row.original.in_manifest}
      />
    ),
  },
  {
    accessorKey: 'minimum_os_version',
    header: 'Min OS',
    cell: ({ row }) => (
      <span className="font-mono text-sm text-muted-foreground">
        {row.original.minimum_os_version ?? '—'}
      </span>
    ),
  },
  {
    accessorKey: 'installer_type',
    header: 'Installer Type',
    cell: ({ row }) =>
      row.original.installer_type ? (
        <Badge variant="outline">{row.original.installer_type}</Badge>
      ) : (
        <span className="text-sm text-muted-foreground">—</span>
      ),
  },
  {
    accessorKey: 'unattended_install',
    header: 'Unattended',
    cell: ({ row }) => (
      <Badge variant={row.original.unattended_install ? 'default' : 'outline'}>
        {row.original.unattended_install ? 'Yes' : 'No'}
      </Badge>
    ),
  },
  {
    accessorKey: 'unattended_uninstall',
    header: 'Unattended Uninstall',
    cell: ({ row }) => (
      <Badge
        variant={row.original.unattended_uninstall ? 'default' : 'outline'}
      >
        {row.original.unattended_uninstall ? 'Yes' : 'No'}
      </Badge>
    ),
  },
  {
    accessorKey: 'restart_action',
    header: 'Restart Action',
    cell: ({ row }) =>
      row.original.restart_action ? (
        <Badge variant="secondary">{row.original.restart_action}</Badge>
      ) : (
        <span className="text-sm text-muted-foreground">—</span>
      ),
  },
  {
    accessorKey: 'updated_at',
    header: 'Updated',
    cell: ({ row }) => (
      <span suppressHydrationWarning className="text-sm text-muted-foreground">
        {formatDate(row.original.updated_at)}
      </span>
    ),
  },
]

const DEFAULT_COLUMN_VISIBILITY: VisibilityState = {
  display_name: true,
  version: true,
  category: true,
  install_count: true,
  failed_install_count: true,
  developer: false,
  catalog_names: true,
  deployment_status: true,
  minimum_os_version: false,
  installer_type: false,
  unattended_install: false,
  unattended_uninstall: false,
  restart_action: false,
  updated_at: true,
}

export default function SoftwarePage() {
  const { canWrite } = useAuth()
  const canEditSoftware = canWrite(PAGE_KEYS.munkiSoftware)

  useDocumentTitle('Munki', 'Software')

  const [listState, setListState] = useAtom(softwarePageListAtom)
  const {
    search,
    category,
    catalog,
    deploymentStatus,
    latestOnly,
    page,
    pageSize,
    sorting,
  } = listState
  const [columnVisibility, setColumnVisibility] = useState<VisibilityState>(
    DEFAULT_COLUMN_VISIBILITY,
  )
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({})
  const [categoryDialogOpen, setCategoryDialogOpen] = useState(false)
  const [catalogsDialogOpen, setCatalogsDialogOpen] = useState(false)
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [clearMetadataCacheOnBulkDelete, setClearMetadataCacheOnBulkDelete] =
    useState(false)
  const clearBulkCacheCheckboxId = useId()
  const [bulkCategoryInput, setBulkCategoryInput] = useState('')
  const [bulkCatalogNames, setBulkCatalogNames] = useState<string[]>([])
  const [uploadDialogOpen, setUploadDialogOpen] = useState(false)

  useEffect(() => {
    if (!canEditSoftware) setRowSelection({})
  }, [canEditSoftware])

  const queryClient = useQueryClient()

  const selectedIds = useMemo(
    () => Object.keys(rowSelection).filter((id) => rowSelection[id]),
    [rowSelection],
  )

  const bulkMutation = useMutation({
    mutationFn: (body: PkgInfoBulkUpdateRequest) =>
      api.post<PkgInfoBulkUpdateResult>('/pkginfo/bulk-update', body),
    onSuccess: (res) => {
      toast.success(`Updated ${res.updated} item(s)`)
      queryClient.invalidateQueries({ queryKey: ['pkginfo'] })
      queryClient.invalidateQueries({ queryKey: ['pkginfo-categories'] })
      queryClient.invalidateQueries({ queryKey: ['catalogs'] })
      setRowSelection({})
      setCategoryDialogOpen(false)
      setCatalogsDialogOpen(false)
      setBulkCategoryInput('')
      setBulkCatalogNames([])
    },
    onError: (err: Error) => toast.error(err.message),
  })

  const deleteMutation = useMutation({
    mutationFn: ({
      ids,
      clearCache,
    }: {
      ids: string[]
      clearCache: boolean
    }) => {
      const q = clearCache ? '?clear_metadata_cache=true' : ''
      return Promise.all(
        ids.map((id) =>
          api.delete<{
            message: string
            metadata_cache_entries_deleted: number
          }>(`/pkginfo/${id}${q}`),
        ),
      )
    },
    onSuccess: (results, { ids, clearCache }) => {
      const totalCache = results.reduce(
        (s, r) => s + (r.metadata_cache_entries_deleted ?? 0),
        0,
      )
      if (ids.length === 1) {
        if (totalCache > 0) {
          toast.success('Removed 1 item from the software catalog', {
            description: `Cleared ${totalCache} metadata cache row(s) so the next AutoPkg run can re-fetch this recipe.`,
          })
        } else if (clearCache) {
          toast.success('Removed 1 item from the software catalog', {
            description:
              'No cache row was removed (not linked to a recipe on a prior ingest, or the cache was already clear).',
          })
        } else {
          toast.success('Removed 1 item from the software catalog')
        }
      } else if (totalCache > 0) {
        toast.success(`Removed ${ids.length} items from the software catalog`, {
          description: `Cleared ${totalCache} metadata cache row(s) in total so the next AutoPkg run can re-fetch where applicable.`,
        })
      } else if (clearCache) {
        toast.success(`Removed ${ids.length} items from the software catalog`, {
          description:
            'No cache rows were removed (items not linked to a recipe, or the cache was already clear).',
        })
      } else {
        toast.success(`Removed ${ids.length} items from the software catalog`)
      }
      queryClient.invalidateQueries({ queryKey: ['pkginfo'] })
      queryClient.invalidateQueries({ queryKey: ['pkginfo-categories'] })
      queryClient.invalidateQueries({ queryKey: ['catalogs'] })
      setRowSelection({})
      setDeleteDialogOpen(false)
      setClearMetadataCacheOnBulkDelete(false)
    },
    onError: (err: Error) => toast.error(err.message),
  })

  const sortBy = sorting[0]?.id ?? 'display_name'
  const sortOrder = sorting[0]?.desc ? 'desc' : 'asc'

  const { data, isLoading } = useQuery({
    queryKey: [
      'pkginfo',
      page,
      pageSize,
      search,
      category,
      catalog,
      deploymentStatus,
      latestOnly,
      sortBy,
      sortOrder,
    ],
    queryFn: () => {
      const params = new URLSearchParams()
      params.set('page', String(page))
      params.set('page_size', String(pageSize))
      params.set('sort_by', sortBy)
      params.set('sort_order', sortOrder)
      if (search) params.set('search', search)
      if (category) params.set('category', category)
      if (catalog) params.set('catalog', catalog)
      if (deploymentStatus) params.set('deployment_status', deploymentStatus)
      if (latestOnly) params.set('latest_only', 'true')
      return api.get<PaginatedResponse<PkgInfoSummary>>(
        `/pkginfo?${params.toString()}`,
      )
    },
  })

  const { data: catalogs } = useQuery({
    queryKey: ['catalogs'],
    queryFn: () => api.get<CatalogRead[]>('/catalogs'),
  })

  const { data: categories } = useQuery({
    queryKey: ['pkginfo-categories'],
    queryFn: () => api.get<string[]>('/pkginfo/categories'),
  })

  const hasFilters = search || category || catalog || deploymentStatus
  const activeFilterCount = [
    search,
    category,
    catalog,
    deploymentStatus,
  ].filter(Boolean).length

  return (
    <div className="flex h-[calc(100vh-3rem)] flex-col gap-4">
      <PageHeading
        icon={Package}
        accent="software"
        title="Software Catalog"
        actions={
          canEditSoftware && (
            <Button variant="outline" onClick={() => setUploadDialogOpen(true)}>
              <Upload className="h-4 w-4" />
              Upload software
            </Button>
          )
        }
      />

      <SoftwareUploadDialog
        open={uploadDialogOpen}
        onOpenChange={setUploadDialogOpen}
        catalogs={catalogs ?? []}
      />

      <PageFilters
        isFiltered={hasFilters}
        activeFilterCount={activeFilterCount}
        onClear={() => {
          setListState((p) => ({
            ...p,
            search: '',
            category: '',
            catalog: '',
            deploymentStatus: '',
            page: 1,
          }))
        }}
        trailing={
          <ColumnVisibilityMenu
            columns={columns}
            columnVisibility={columnVisibility}
            onColumnVisibilityChange={setColumnVisibility}
          />
        }
      >
        <div className="relative max-w-sm flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search software..."
            value={search}
            onChange={(e) => {
              setListState((p) => ({
                ...p,
                search: e.target.value,
                page: 1,
              }))
            }}
            className="pl-9"
          />
        </div>

        <Select
          value={category || '_all'}
          onValueChange={(v) => {
            setListState((p) => ({
              ...p,
              category: v === '_all' ? '' : v,
              page: 1,
            }))
          }}
        >
          <SelectTrigger className="w-full md:w-[160px]">
            <SelectValue placeholder="Category" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="_all">All Categories</SelectItem>
            {(categories ?? []).map((c) => (
              <SelectItem key={c} value={c}>
                {c}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={catalog || '_all'}
          onValueChange={(v) => {
            setListState((p) => ({
              ...p,
              catalog: v === '_all' ? '' : v,
              page: 1,
            }))
          }}
        >
          <SelectTrigger className="w-full md:w-[160px]">
            <SelectValue placeholder="Catalog" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="_all">All Catalogs</SelectItem>
            {catalogs?.map((c) => (
              <SelectItem key={c.id} value={c.name}>
                {c.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={deploymentStatus || '__all__'}
          onValueChange={(v) => {
            setListState((p) => ({
              ...p,
              deploymentStatus: v === '__all__' ? '' : v,
              page: 1,
            }))
          }}
        >
          <SelectTrigger className="w-full md:w-[180px]">
            <SelectValue placeholder="Deployment" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__all__">All deployments</SelectItem>
            <SelectItem value="fully_deployed">Fully deployed</SelectItem>
            <SelectItem value="sharding">Sharding</SelectItem>
            <SelectItem value="pending_rollout">Awaiting rollout</SelectItem>
            <SelectItem value="paused">Paused</SelectItem>
            <SelectItem value="not_in_production">Not in production</SelectItem>
          </SelectContent>
        </Select>

        <div className="flex items-center gap-2 rounded-md border bg-muted/30 px-3 py-1.5">
          <Switch
            id="software-latest-only"
            checked={latestOnly}
            onCheckedChange={(checked) => {
              setListState((p) => ({
                ...p,
                latestOnly: checked,
                page: 1,
              }))
            }}
          />
          <Label
            htmlFor="software-latest-only"
            className="cursor-pointer text-sm font-normal"
          >
            Latest only
          </Label>
        </div>
      </PageFilters>

      {selectedIds.length > 0 && (
        <div
          className={cn(
            'flex flex-wrap items-center gap-2 rounded-md border bg-muted/40 px-3 py-2 text-sm',
            munkiAccents.software.pageTitle,
          )}
        >
          <Tags
            className="h-4 w-4 shrink-0 text-muted-foreground"
            aria-hidden
          />
          <span className="font-medium tabular-nums">
            {selectedIds.length} selected
          </span>
          <div className="ml-auto flex flex-wrap items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setBulkCategoryInput('')
                setCategoryDialogOpen(true)
              }}
            >
              Set category
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setBulkCatalogNames([])
                setCatalogsDialogOpen(true)
              }}
            >
              Set catalogs
            </Button>
            <Button
              variant="destructive"
              size="sm"
              onClick={() => setDeleteDialogOpen(true)}
            >
              <Trash2 className="h-4 w-4" />
              Delete
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setRowSelection({})}
            >
              Clear selection
            </Button>
          </div>
        </div>
      )}

      <Dialog open={categoryDialogOpen} onOpenChange={setCategoryDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Set category</DialogTitle>
            <DialogDescription>
              Apply the same category to {selectedIds.length} selected item(s).
              Leave empty and choose &quot;Clear category&quot; to remove the
              category.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-2 py-2">
            <Label htmlFor="bulk-category">Category</Label>
            <Input
              id="bulk-category"
              value={bulkCategoryInput}
              onChange={(e) => setBulkCategoryInput(e.target.value)}
              placeholder="e.g. Productivity"
              list="software-category-suggestions"
            />
            <datalist id="software-category-suggestions">
              {(categories ?? []).map((c) => (
                <option key={c} value={c} />
              ))}
            </datalist>
          </div>
          <DialogFooter className="gap-2 sm:justify-between">
            <Button
              type="button"
              variant="outline"
              onClick={() =>
                bulkMutation.mutate({
                  pkginfo_ids: selectedIds,
                  category: null,
                })
              }
              disabled={bulkMutation.isPending}
            >
              Clear category
            </Button>
            <Button
              type="button"
              onClick={() =>
                bulkMutation.mutate({
                  pkginfo_ids: selectedIds,
                  category: bulkCategoryInput.trim() || null,
                })
              }
              disabled={bulkMutation.isPending}
            >
              Apply
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={catalogsDialogOpen} onOpenChange={setCatalogsDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Set catalogs</DialogTitle>
            <DialogDescription>
              Replace catalog membership for {selectedIds.length} selected
              item(s) with the catalogs you choose below.
            </DialogDescription>
          </DialogHeader>
          <div className="max-h-64 space-y-2 overflow-y-auto py-2">
            {(catalogs ?? [])
              .slice()
              .sort((a, b) => a.name.localeCompare(b.name))
              .map((cat) => (
                <label
                  key={cat.id}
                  className="flex cursor-pointer items-center gap-2 rounded-md border border-transparent px-2 py-1.5 hover:bg-muted/60"
                >
                  <Checkbox
                    checked={bulkCatalogNames.includes(cat.name)}
                    onCheckedChange={(v) => {
                      const on = !!v
                      setBulkCatalogNames((prev) =>
                        on
                          ? prev.includes(cat.name)
                            ? prev
                            : [...prev, cat.name]
                          : prev.filter((n) => n !== cat.name),
                      )
                    }}
                  />
                  <span className="text-sm">{cat.name}</span>
                  {cat.is_production && (
                    <Badge variant="secondary" className="ml-auto text-xs">
                      Production
                    </Badge>
                  )}
                </label>
              ))}
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setCatalogsDialogOpen(false)}
            >
              Cancel
            </Button>
            <Button
              type="button"
              onClick={() =>
                bulkMutation.mutate({
                  pkginfo_ids: selectedIds,
                  catalog_names: bulkCatalogNames,
                })
              }
              disabled={bulkMutation.isPending}
            >
              Apply
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={deleteDialogOpen}
        onOpenChange={(open) => {
          setDeleteDialogOpen(open)
          if (!open) setClearMetadataCacheOnBulkDelete(false)
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Remove from software catalog</DialogTitle>
            <DialogDescription>
              {selectedIds.length === 1
                ? 'This marks the item as deleted and removes it from Munki catalogs. Clients will no longer see it as an optional install from those catalogs.'
                : `This marks ${selectedIds.length} items as deleted and removes them from Munki catalogs. Clients will no longer see them as optional installs from those catalogs.`}
            </DialogDescription>
          </DialogHeader>
          <div className="flex items-start gap-2 rounded-md border p-3">
            <Checkbox
              id={clearBulkCacheCheckboxId}
              checked={clearMetadataCacheOnBulkDelete}
              onCheckedChange={(c) => setClearMetadataCacheOnBulkDelete(!!c)}
              disabled={deleteMutation.isPending}
            />
            <label
              htmlFor={clearBulkCacheCheckboxId}
              className="cursor-pointer text-left text-sm leading-tight"
            >
              <span className="font-medium">Also clear metadata cache</span>
              <span className="mt-0.5 block text-xs text-muted-foreground">
                Lets the next cloud/local AutoPkg run re-notice these recipes
                instead of reporting no change. Only applies to items that were
                imported with a recipe identifier.
              </span>
            </label>
          </div>
          <DialogFooter className="gap-2 sm:justify-between">
            <Button
              type="button"
              variant="outline"
              onClick={() => setDeleteDialogOpen(false)}
              disabled={deleteMutation.isPending}
            >
              Cancel
            </Button>
            <Button
              type="button"
              variant="destructive"
              onClick={() =>
                deleteMutation.mutate({
                  ids: selectedIds,
                  clearCache: clearMetadataCacheOnBulkDelete,
                })
              }
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending ? 'Removing…' : 'Remove'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <div className="min-h-0 flex-1">
        <DataTable
          columns={columns}
          data={data?.items ?? []}
          pageCount={data?.total_pages ?? 1}
          page={page}
          pageSize={pageSize}
          total={data?.total}
          onPageChange={(nextPage) => {
            setListState((p) => ({ ...p, page: nextPage }))
          }}
          onPageSizeChange={(size) => {
            setListState((p) => ({ ...p, pageSize: size, page: 1 }))
          }}
          isLoading={isLoading}
          sorting={sorting}
          onSortingChange={(next) => {
            setListState((p) => ({ ...p, sorting: next, page: 1 }))
          }}
          defaultColumnVisibility={DEFAULT_COLUMN_VISIBILITY}
          columnVisibility={columnVisibility}
          onColumnVisibilityChange={setColumnVisibility}
          hideColumnPicker
          enableRowSelection={canEditSoftware}
          rowSelection={rowSelection}
          onRowSelectionChange={setRowSelection}
          getRowId={(row) => row.id}
        />
      </div>
    </div>
  )
}
