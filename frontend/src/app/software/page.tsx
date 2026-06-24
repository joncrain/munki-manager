import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { RowSelectionState, VisibilityState } from '@tanstack/react-table'
import { useAtom } from 'jotai'
import { Package, Search, Tags, Trash2, Upload } from 'lucide-react'
import { parseAsString, useQueryState } from 'nuqs'
import { useCallback, useEffect, useId, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import { useAuth } from '@/components/auth-provider'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { ColumnVisibilityMenu, DataTable } from '@/components/data-table'
import { PageFilters } from '@/components/page-filters'
import { PageHeading } from '@/components/page-heading'
import {
  makeSoftwareListColumns,
  softwareListDefaultColumnVisibility,
} from '@/components/software/software-list-columns'
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
import { munkiAccents } from '@/lib/munki-accents'
import { PAGE_KEYS } from '@/lib/page-keys'
import { cn } from '@/lib/utils'

const DEPLOYMENT_FILTER_LABELS: Record<string, string> = {
  fully_deployed: 'Fully deployed',
  sharding: 'Sharding',
  pending_rollout: 'Awaiting rollout',
  paused: 'Paused',
  not_in_production: 'Not in production',
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
    softwareListDefaultColumnVisibility,
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

  const [promotionEligible, setPromotionEligible] = useQueryState(
    'promotion_eligible',
    parseAsString.withDefault(''),
  )
  const [rolloutQueue, setRolloutQueue] = useQueryState(
    'rollout_queue',
    parseAsString.withDefault(''),
  )
  const isPromotionEligibleFilter = promotionEligible === 'true'
  const isRolloutQueueFilter = rolloutQueue === 'true'

  useEffect(() => {
    if (!canEditSoftware) setRowSelection({})
  }, [canEditSoftware])

  const [searchParams] = useSearchParams()
  useEffect(() => {
    const deploymentFromUrl = searchParams.get('deployment_status')?.trim()
    if (!deploymentFromUrl) return
    setListState((prev) =>
      prev.deploymentStatus === deploymentFromUrl
        ? prev
        : { ...prev, deploymentStatus: deploymentFromUrl, page: 1 },
    )
  }, [searchParams, setListState])

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
      isPromotionEligibleFilter,
      isRolloutQueueFilter,
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
      if (isPromotionEligibleFilter) params.set('promotion_eligible', 'true')
      if (isRolloutQueueFilter) params.set('rollout_queue', 'true')
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

  const latestOnlyDeviatesFromDefault = !latestOnly

  const hasSheetFilters = Boolean(
    category ||
      catalog ||
      deploymentStatus ||
      isPromotionEligibleFilter ||
      isRolloutQueueFilter ||
      latestOnlyDeviatesFromDefault,
  )
  const activeFilterCount = [
    category,
    catalog,
    deploymentStatus,
    isPromotionEligibleFilter,
    isRolloutQueueFilter,
    latestOnlyDeviatesFromDefault,
  ].filter(Boolean).length

  const onCategoryFilter = useCallback(
    (nextCategory: string) => {
      setListState((p) => ({ ...p, category: nextCategory, page: 1 }))
    },
    [setListState],
  )

  const onCatalogFilter = useCallback(
    (nextCatalog: string) => {
      setListState((p) => ({ ...p, catalog: nextCatalog, page: 1 }))
    },
    [setListState],
  )

  const onDeploymentStatusFilter = useCallback(
    (nextDeploymentStatus: string) => {
      setListState((p) => ({
        ...p,
        deploymentStatus: nextDeploymentStatus,
        page: 1,
      }))
    },
    [setListState],
  )

  const columns = useMemo(
    () =>
      makeSoftwareListColumns({
        onCategoryFilter,
        onCatalogFilter,
        onDeploymentStatusFilter,
      }),
    [onCatalogFilter, onCategoryFilter, onDeploymentStatusFilter],
  )

  const activeFilters = [
    ...(category
      ? [
          {
            id: 'category',
            label: `Category: ${category}`,
            onRemove: () => {
              setListState((p) => ({ ...p, category: '', page: 1 }))
            },
          },
        ]
      : []),
    ...(catalog
      ? [
          {
            id: 'catalog',
            label: `Catalog: ${catalog}`,
            onRemove: () => {
              setListState((p) => ({ ...p, catalog: '', page: 1 }))
            },
          },
        ]
      : []),
    ...(deploymentStatus
      ? [
          {
            id: 'deploymentStatus',
            label: `Deployment: ${DEPLOYMENT_FILTER_LABELS[deploymentStatus] ?? deploymentStatus}`,
            onRemove: () => {
              setListState((p) => ({ ...p, deploymentStatus: '', page: 1 }))
            },
          },
        ]
      : []),
    ...(latestOnlyDeviatesFromDefault
      ? [
          {
            id: 'latestOnly',
            label: 'All versions',
            onRemove: () => {
              setListState((p) => ({ ...p, latestOnly: true, page: 1 }))
            },
          },
        ]
      : []),
    ...(isPromotionEligibleFilter
      ? [
          {
            id: 'promotionEligible',
            label: 'Promotion eligible',
            onRemove: () => {
              void setPromotionEligible(null)
              setListState((p) => ({ ...p, page: 1 }))
            },
          },
        ]
      : []),
    ...(isRolloutQueueFilter
      ? [
          {
            id: 'rolloutQueue',
            label: 'Rollout queue',
            onRemove: () => {
              void setRolloutQueue(null)
              setListState((p) => ({ ...p, page: 1 }))
            },
          },
        ]
      : []),
  ]

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
        isFiltered={hasSheetFilters}
        activeFilterCount={activeFilterCount}
        activeFilters={activeFilters}
        onClear={() => {
          void setPromotionEligible(null)
          void setRolloutQueue(null)
          setListState((p) => ({
            ...p,
            category: '',
            catalog: '',
            deploymentStatus: '',
            latestOnly: true,
            page: 1,
          }))
        }}
        trailing={
          <ColumnVisibilityMenu
            columns={columns}
            columnVisibility={columnVisibility}
            defaultColumnVisibility={softwareListDefaultColumnVisibility}
            onColumnVisibilityChange={setColumnVisibility}
          />
        }
        search={
          <div className="relative max-w-sm">
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
        }
      >
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
          <SelectTrigger className="w-full">
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
          <SelectTrigger className="w-full">
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
          <SelectTrigger className="w-full">
            <SelectValue placeholder="Deployment" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__all__">All Deployments</SelectItem>
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
              .map((cat) => {
                const checkboxId = `bulk-catalog-${cat.id}`
                return (
                  <label
                    key={cat.id}
                    htmlFor={checkboxId}
                    className="flex cursor-pointer items-center gap-2 rounded-md border border-transparent px-2 py-1.5 hover:bg-muted/60"
                  >
                    <Checkbox
                      id={checkboxId}
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
                )
              })}
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

      <ConfirmDialog
        open={deleteDialogOpen}
        onOpenChange={(open) => {
          setDeleteDialogOpen(open)
          if (!open) setClearMetadataCacheOnBulkDelete(false)
        }}
        title="Remove from software catalog"
        description={
          selectedIds.length === 1
            ? 'This marks the item as deleted and removes it from Munki catalogs. Clients will no longer see it as an optional install from those catalogs.'
            : `This marks ${selectedIds.length} items as deleted and removes them from Munki catalogs. Clients will no longer see them as optional installs from those catalogs.`
        }
        confirmLabel="Remove"
        pendingLabel="Removing…"
        isPending={deleteMutation.isPending}
        onConfirm={() =>
          deleteMutation.mutate({
            ids: selectedIds,
            clearCache: clearMetadataCacheOnBulkDelete,
          })
        }
      >
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
      </ConfirmDialog>

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
          defaultColumnVisibility={softwareListDefaultColumnVisibility}
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
