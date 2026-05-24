import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { ColumnDef } from '@tanstack/react-table'
import {
  FolderOpen,
  LayoutGrid,
  Loader2,
  Plus,
  Save,
  Table2,
  Trash2,
} from 'lucide-react'
import { parseAsStringLiteral, useQueryState } from 'nuqs'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'
import { useAuth } from '@/components/auth-provider'
import { DataTable } from '@/components/data-table'
import { PageHeading } from '@/components/page-heading'
import { CatalogSoftwareAvatarCircles } from '@/components/software-avatar-circles'
import { SoftwareIcon } from '@/components/software-icon'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'
import { Switch } from '@/components/ui/switch'
import { useDocumentTitle } from '@/hooks/use-document-title'
import { api, type CatalogRead, type PkgInfoSummary } from '@/lib/api'
import { formatDate } from '@/lib/format'
import { munkiAccents } from '@/lib/munki-accents'
import { PAGE_KEYS } from '@/lib/page-keys'
import { cn } from '@/lib/utils'

function catalogReadTitle(c: CatalogRead) {
  return c.display_name?.trim() || c.name
}

export default function CatalogsPage() {
  useDocumentTitle('Munki', 'Catalogs')
  const { canWrite } = useAuth()
  const canEditCatalogs = canWrite(PAGE_KEYS.munkiCatalogs)

  const queryClient = useQueryClient()
  const [createOpen, setCreateOpen] = useState(false)
  const [name, setName] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [description, setDescription] = useState('')
  const [isProduction, setIsProduction] = useState(false)
  const [isQuarantine, setIsQuarantine] = useState(false)

  const [deleteCatalog, setDeleteCatalog] = useState<CatalogRead | null>(null)
  const [viewCatalog, setViewCatalog] = useState<CatalogRead | null>(null)

  const [listView, setListView] = useQueryState(
    'view',
    parseAsStringLiteral(['cards', 'table'] as const).withDefault('cards'),
  )

  const { data: catalogs, isLoading } = useQuery({
    queryKey: ['catalogs'],
    queryFn: () => api.get<CatalogRead[]>('/catalogs'),
  })

  const createMutation = useMutation({
    mutationFn: (payload: {
      name: string
      display_name?: string
      description?: string
      is_production: boolean
      is_quarantine: boolean
    }) => api.post<CatalogRead>('/catalogs', payload),
    onSuccess: (created) => {
      toast.success(`Catalog "${created.name}" created`)
      queryClient.invalidateQueries({ queryKey: ['catalogs'] })
      setCreateOpen(false)
      resetCreateForm()
    },
    onError: (err: Error) => toast.error(`Failed to create: ${err.message}`),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/catalogs/${id}`),
    onSuccess: () => {
      toast.success('Catalog deleted')
      queryClient.invalidateQueries({ queryKey: ['catalogs'] })
      setDeleteCatalog(null)
    },
    onError: (err: Error) => toast.error(`Failed to delete: ${err.message}`),
  })

  function resetCreateForm() {
    setName('')
    setDisplayName('')
    setDescription('')
    setIsProduction(false)
    setIsQuarantine(false)
  }

  const handleCreate = () => {
    const trimmed = name.trim()
    if (!trimmed) return
    createMutation.mutate({
      name: trimmed,
      display_name: displayName.trim() || undefined,
      description: description.trim() || undefined,
      is_production: isProduction,
      is_quarantine: isQuarantine,
    })
  }

  const tableColumns = useMemo<ColumnDef<CatalogRead>[]>(
    () => [
      {
        id: 'title',
        header: 'Catalog',
        accessorFn: (row) => catalogReadTitle(row),
        cell: ({ row }) => {
          const c = row.original
          return (
            <div className="min-w-0 max-w-[min(100%,20rem)]">
              <button
                type="button"
                onClick={() => setViewCatalog(c)}
                className="text-left font-medium text-primary underline-offset-4 hover:underline"
              >
                {catalogReadTitle(c)}
              </button>
              {catalogReadTitle(c) !== c.name ? (
                <div className="truncate font-mono text-xs text-muted-foreground">
                  {c.name}
                </div>
              ) : null}
            </div>
          )
        },
      },
      {
        id: 'production',
        header: 'Production',
        accessorKey: 'is_production',
        cell: ({ row }) =>
          row.original.is_production ? (
            <Badge variant="default">Production</Badge>
          ) : (
            <span className="text-muted-foreground">—</span>
          ),
      },
      {
        id: 'quarantine',
        header: 'Quarantine',
        accessorKey: 'is_quarantine',
        cell: ({ row }) =>
          row.original.is_quarantine ? (
            <Badge
              variant="default"
              className="bg-gruvbox-yellow text-primary-foreground"
            >
              Quarantine
            </Badge>
          ) : (
            <span className="text-muted-foreground">—</span>
          ),
      },
      {
        id: 'item_count',
        header: 'Titles',
        accessorKey: 'item_count',
        cell: ({ row }) => (
          <span
            className="tabular-nums"
            style={{ fontVariantNumeric: 'tabular-nums' }}
          >
            {row.original.item_count}
          </span>
        ),
      },
      {
        id: 'description',
        header: 'Description',
        accessorFn: (row) => row.description ?? '',
        cell: ({ row }) => {
          const d = row.original.description?.trim()
          return d ? (
            <span className="line-clamp-2 max-w-md text-sm text-muted-foreground">
              {d}
            </span>
          ) : (
            <span className="text-muted-foreground">—</span>
          )
        },
      },
      {
        id: 'created_at',
        header: 'Created',
        accessorKey: 'created_at',
        cell: ({ row }) => (
          <span
            suppressHydrationWarning
            className="whitespace-nowrap text-sm text-muted-foreground"
          >
            {formatDate(row.original.created_at)}
          </span>
        ),
      },
      ...(canEditCatalogs
        ? [
            {
              id: 'actions',
              header: '',
              enableSorting: false,
              cell: ({ row }) => (
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 text-muted-foreground hover:text-destructive"
                  aria-label={`Delete ${row.original.name}`}
                  onClick={() => setDeleteCatalog(row.original)}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              ),
            } satisfies ColumnDef<CatalogRead>,
          ]
        : []),
    ],
    [canEditCatalogs],
  )

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12 text-muted-foreground">
        Loading…
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <PageHeading icon={FolderOpen} accent="catalogs" title="Catalogs" />
        <div className="flex flex-wrap items-center justify-end gap-2">
          <div className="inline-flex items-center rounded-md border bg-muted/30 p-0.5">
            <Button
              type="button"
              variant={listView === 'cards' ? 'secondary' : 'ghost'}
              size="sm"
              className="h-8 gap-1.5 px-2.5"
              aria-pressed={listView === 'cards'}
              aria-label="Card layout"
              onClick={() => setListView('cards')}
            >
              <LayoutGrid className="h-4 w-4" aria-hidden />
              Cards
            </Button>
            <Button
              type="button"
              variant={listView === 'table' ? 'secondary' : 'ghost'}
              size="sm"
              className="h-8 gap-1.5 px-2.5"
              aria-pressed={listView === 'table'}
              aria-label="Table layout"
              onClick={() => setListView('table')}
            >
              <Table2 className="h-4 w-4" aria-hidden />
              Table
            </Button>
          </div>
          {canEditCatalogs ? (
            <Dialog
              open={createOpen}
              onOpenChange={(v) => {
                setCreateOpen(v)
                if (!v) resetCreateForm()
              }}
            >
              <DialogTrigger asChild>
                <Button>
                  <Plus className="h-4 w-4" />
                  New Catalog
                </Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Create Catalog</DialogTitle>
                  <DialogDescription>
                    Create a new Munki catalog. Software can be assigned to it
                    afterwards.
                  </DialogDescription>
                </DialogHeader>
                <div className="grid gap-4 py-4">
                  <div className="grid gap-2">
                    <Label htmlFor="catalog-name">Name</Label>
                    <Input
                      id="catalog-name"
                      placeholder="e.g. production"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') handleCreate()
                      }}
                    />
                  </div>
                  <div className="grid gap-2">
                    <Label htmlFor="catalog-display-name">
                      Display name (optional)
                    </Label>
                    <Input
                      id="catalog-display-name"
                      placeholder="e.g. Production software"
                      value={displayName}
                      onChange={(e) => setDisplayName(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') handleCreate()
                      }}
                    />
                  </div>
                  <div className="grid gap-2">
                    <Label htmlFor="catalog-description">
                      Description (optional)
                    </Label>
                    <Input
                      id="catalog-description"
                      placeholder="e.g. Production software catalog"
                      value={description}
                      onChange={(e) => setDescription(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') handleCreate()
                      }}
                    />
                  </div>
                  <div className="flex items-center gap-3">
                    <Switch
                      id="catalog-production"
                      checked={isProduction}
                      onCheckedChange={setIsProduction}
                    />
                    <Label htmlFor="catalog-production">
                      Production catalog
                    </Label>
                  </div>
                  <div className="flex items-center gap-3">
                    <Switch
                      id="catalog-quarantine"
                      checked={isQuarantine}
                      onCheckedChange={setIsQuarantine}
                    />
                    <Label htmlFor="catalog-quarantine">
                      Quarantine catalog (pending import approvals)
                    </Label>
                  </div>
                </div>
                <DialogFooter>
                  <Button
                    onClick={handleCreate}
                    disabled={!name.trim() || createMutation.isPending}
                  >
                    {createMutation.isPending ? 'Creating...' : 'Create'}
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          ) : null}
        </div>
      </div>

      {/* Delete Confirmation Dialog */}
      <Dialog
        open={!!deleteCatalog}
        onOpenChange={(v) => {
          if (!v) setDeleteCatalog(null)
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Catalog</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete &ldquo;{deleteCatalog?.name}
              &rdquo;? This action cannot be undone.
              {(deleteCatalog?.item_count ?? 0) > 0 && (
                <span className="mt-2 block font-medium text-destructive">
                  This catalog has {deleteCatalog?.item_count} assigned items
                  and cannot be deleted until they are removed.
                </span>
              )}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteCatalog(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() =>
                deleteCatalog && deleteMutation.mutate(deleteCatalog.id)
              }
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending ? 'Deleting...' : 'Delete'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {viewCatalog && (
        <CatalogDetailDialog
          catalog={viewCatalog}
          onClose={() => setViewCatalog(null)}
          onUpdated={setViewCatalog}
          readOnly={!canEditCatalogs}
        />
      )}

      {!catalogs?.length ? (
        <p className="text-muted-foreground">
          No catalogs found. Click &ldquo;New Catalog&rdquo; to create one.
        </p>
      ) : listView === 'table' ? (
        <DataTable<CatalogRead, unknown>
          columns={tableColumns}
          data={catalogs}
          getRowId={(row) => row.id}
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {catalogs.map((catalog) => (
            <Card
              key={catalog.id}
              className={cn(munkiAccents.catalogs.catalogGridCard)}
              onClick={() => setViewCatalog(catalog)}
            >
              <CardHeader className="flex flex-row items-center justify-between space-y-0">
                <CardTitle className="flex flex-col gap-0.5">
                  <span className="flex items-center gap-2">
                    <FolderOpen
                      className={cn('h-5 w-5', munkiAccents.catalogs.icon)}
                      aria-hidden
                    />
                    {catalog.display_name?.trim() || catalog.name}
                  </span>
                  {catalog.display_name?.trim() &&
                  catalog.display_name.trim() !== catalog.name ? (
                    <span className="text-xs font-normal text-muted-foreground">
                      {catalog.name}
                    </span>
                  ) : null}
                </CardTitle>
                <div className="flex flex-wrap items-center gap-2">
                  {catalog.is_production && (
                    <Badge variant="default">Production</Badge>
                  )}
                  {catalog.is_quarantine && (
                    <Badge
                      variant="default"
                      className="bg-gruvbox-yellow text-primary-foreground"
                    >
                      Quarantine
                    </Badge>
                  )}
                  {canEditCatalogs ? (
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 text-muted-foreground hover:text-destructive"
                      aria-label={`Delete ${catalog.name}`}
                      onClick={(e) => {
                        e.stopPropagation()
                        setDeleteCatalog(catalog)
                      }}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  ) : null}
                </div>
              </CardHeader>
              <CardContent>
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p
                      className="text-2xl font-bold"
                      style={{ fontVariantNumeric: 'tabular-nums' }}
                    >
                      {catalog.item_count}
                    </p>
                    <p className="text-sm text-muted-foreground">
                      software titles
                    </p>
                  </div>
                  <CatalogSoftwareAvatarCircles
                    catalogName={catalog.name}
                    itemCount={catalog.item_count}
                    className="shrink-0"
                  />
                </div>
                {catalog.description && (
                  <p className="mt-2 text-sm">{catalog.description}</p>
                )}
                <p
                  suppressHydrationWarning
                  className="mt-2 text-xs text-muted-foreground"
                >
                  Created {formatDate(catalog.created_at)}
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}

function CatalogDetailDialog({
  catalog,
  onClose,
  onUpdated,
  readOnly = false,
}: {
  catalog: CatalogRead
  onClose: () => void
  onUpdated: (c: CatalogRead) => void
  readOnly?: boolean
}) {
  const queryClient = useQueryClient()
  const [editDisplayName, setEditDisplayName] = useState(
    catalog.display_name ?? '',
  )
  const [editDescription, setEditDescription] = useState(
    catalog.description ?? '',
  )
  const [editIsProduction, setEditIsProduction] = useState(
    catalog.is_production,
  )
  const [editIsQuarantine, setEditIsQuarantine] = useState(
    catalog.is_quarantine,
  )

  useEffect(() => {
    setEditDisplayName(catalog.display_name ?? '')
    setEditDescription(catalog.description ?? '')
    setEditIsProduction(catalog.is_production)
    setEditIsQuarantine(catalog.is_quarantine)
  }, [
    catalog.display_name,
    catalog.description,
    catalog.is_production,
    catalog.is_quarantine,
  ])

  const { data: items, isLoading } = useQuery({
    queryKey: ['catalog-items', catalog.id],
    queryFn: () => api.get<PkgInfoSummary[]>(`/catalogs/${catalog.id}/items`),
  })

  const updateMutation = useMutation({
    mutationFn: ({
      id,
      ...payload
    }: {
      id: string
      display_name?: string | null
      description?: string
      is_production?: boolean
      is_quarantine?: boolean
    }) => api.put<CatalogRead>(`/catalogs/${id}`, payload),
    onSuccess: (updated) => {
      toast.success(`Catalog "${updated.name}" updated`)
      queryClient.invalidateQueries({ queryKey: ['catalogs'] })
      onUpdated(updated)
    },
    onError: (err: Error) => toast.error(`Failed to update: ${err.message}`),
  })

  const trimmedDisplay = editDisplayName.trim()
  const catalogDisplay = (catalog.display_name ?? '').trim()
  const trimmedDesc = editDescription.trim()
  const catalogDesc = (catalog.description ?? '').trim()
  const isDirty =
    trimmedDisplay !== catalogDisplay ||
    trimmedDesc !== catalogDesc ||
    editIsProduction !== catalog.is_production ||
    editIsQuarantine !== catalog.is_quarantine

  const handleSave = () => {
    updateMutation.mutate({
      id: catalog.id,
      display_name: trimmedDisplay || null,
      description: trimmedDesc || undefined,
      is_production: editIsProduction,
      is_quarantine: editIsQuarantine,
    })
  }

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="flex max-h-[85vh] flex-col gap-0 overflow-hidden sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex flex-col items-start gap-1">
            <span className="flex flex-wrap items-center gap-2">
              <FolderOpen
                className={cn('h-5 w-5', munkiAccents.catalogs.icon)}
              />
              {catalog.display_name?.trim() || catalog.name}
              {editIsProduction && (
                <Badge variant="default" className="shrink-0">
                  Production
                </Badge>
              )}
              {editIsQuarantine && (
                <Badge
                  variant="default"
                  className="shrink-0 bg-gruvbox-yellow text-primary-foreground"
                >
                  Quarantine
                </Badge>
              )}
            </span>
            {catalog.display_name?.trim() &&
            catalog.display_name.trim() !== catalog.name ? (
              <span className="text-sm font-normal text-muted-foreground">
                {catalog.name}
              </span>
            ) : null}
          </DialogTitle>
          <DialogDescription>
            {catalog.item_count} software title
            {catalog.item_count !== 1 ? 's' : ''} in this catalog. The catalog
            identifier ({catalog.name}) cannot be changed.
          </DialogDescription>
        </DialogHeader>

        <div className="grid shrink-0 gap-4 py-4">
          <div className="grid gap-2">
            <Label htmlFor="catalog-detail-display-name">
              Display name (optional)
            </Label>
            <Input
              id="catalog-detail-display-name"
              placeholder="e.g. Production software"
              value={editDisplayName}
              readOnly={readOnly}
              onChange={(e) => setEditDisplayName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && isDirty && !updateMutation.isPending) {
                  e.preventDefault()
                  handleSave()
                }
              }}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="catalog-detail-description">Description</Label>
            <Input
              id="catalog-detail-description"
              placeholder="e.g. Production software catalog"
              value={editDescription}
              readOnly={readOnly}
              onChange={(e) => setEditDescription(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && isDirty && !updateMutation.isPending) {
                  e.preventDefault()
                  handleSave()
                }
              }}
            />
          </div>
          <div className="flex items-center gap-3">
            <Switch
              id="catalog-detail-production"
              checked={editIsProduction}
              onCheckedChange={setEditIsProduction}
              disabled={readOnly}
            />
            <Label htmlFor="catalog-detail-production">
              Production catalog
            </Label>
          </div>
          <div className="flex items-center gap-3">
            <Switch
              id="catalog-detail-quarantine"
              checked={editIsQuarantine}
              onCheckedChange={setEditIsQuarantine}
              disabled={readOnly}
            />
            <Label htmlFor="catalog-detail-quarantine">
              Quarantine catalog (pending import approvals)
            </Label>
          </div>
          {!readOnly ? (
            <div className="flex justify-end">
              <Button
                type="button"
                onClick={handleSave}
                disabled={!isDirty || updateMutation.isPending}
              >
                {updateMutation.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                ) : (
                  <Save className="h-4 w-4" aria-hidden />
                )}
                {updateMutation.isPending ? 'Saving…' : 'Save changes'}
              </Button>
            </div>
          ) : null}
        </div>

        <Separator className="shrink-0" />

        <div className="min-h-0 flex-1 overflow-hidden pt-4">
          <p className="mb-2 text-sm font-medium">Software in this catalog</p>
          <div className="max-h-[min(42vh,24rem)] overflow-y-auto rounded-md border">
            {isLoading ? (
              <div className="flex items-center justify-center py-8 text-muted-foreground">
                Loading…
              </div>
            ) : items?.length ? (
              <div className="divide-y">
                {items.map((item) => (
                  <Link
                    key={item.id}
                    to={`/software/${item.id}`}
                    className="flex items-center gap-3 rounded-md px-2 py-2.5 transition-colors hover:bg-accent/50"
                  >
                    <SoftwareIcon
                      name={item.name}
                      displayName={item.display_name}
                      size="sm"
                    />
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-medium text-sm">
                        {item.display_name || item.name}
                      </p>
                      <p className="truncate text-xs text-muted-foreground">
                        {item.name} — {item.version}
                      </p>
                    </div>
                    {item.category && (
                      <Badge variant="outline" className="shrink-0 text-xs">
                        {item.category}
                      </Badge>
                    )}
                  </Link>
                ))}
              </div>
            ) : (
              <p className="py-8 text-center text-sm text-muted-foreground">
                No software titles in this catalog.
              </p>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
