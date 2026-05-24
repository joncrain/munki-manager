import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { ColumnDef } from '@tanstack/react-table'
import { FileText, LayoutGrid, Plus, Table2, Trash2 } from 'lucide-react'
import { parseAsStringLiteral, useQueryState } from 'nuqs'
import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { useAuth } from '@/components/auth-provider'
import { DataTable } from '@/components/data-table'
import { PageHeading } from '@/components/page-heading'
import { SoftwareNameAvatarCircles } from '@/components/software-avatar-circles'
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
import { useDocumentTitle } from '@/hooks/use-document-title'
import { api, type ManifestRead } from '@/lib/api'
import { formatDateTime } from '@/lib/format'
import { parseManifestItemRef } from '@/lib/manifest-item-ref'
import { manifestTitle, manifestTitleForName } from '@/lib/manifest-title'
import { munkiAccents } from '@/lib/munki-accents'
import { PAGE_KEYS } from '@/lib/page-keys'
import { cn } from '@/lib/utils'

const MANIFEST_CARD_AVATAR_MAX = 8

export default function ManifestsPage() {
  useDocumentTitle('Munki', 'Manifests')
  const { canWrite } = useAuth()
  const canEditManifests = canWrite(PAGE_KEYS.munkiManifests)

  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [createOpen, setCreateOpen] = useState(false)
  const [name, setName] = useState('')
  const [displayName, setDisplayName] = useState('')

  const [deleteManifest, setDeleteManifest] = useState<ManifestRead | null>(
    null,
  )

  const [view, setView] = useQueryState(
    'view',
    parseAsStringLiteral(['cards', 'table'] as const).withDefault('cards'),
  )

  const { data: manifests, isLoading } = useQuery({
    queryKey: ['manifests'],
    queryFn: () => api.get<ManifestRead[]>('/manifests'),
  })

  const createMutation = useMutation({
    mutationFn: (payload: { name: string; display_name?: string }) =>
      api.post<ManifestRead>('/manifests', payload),
    onSuccess: (created) => {
      toast.success(`Manifest "${manifestTitle(created)}" created`)
      queryClient.invalidateQueries({ queryKey: ['manifests'] })
      setCreateOpen(false)
      setName('')
      setDisplayName('')
      navigate(`/manifests/${created.id}`)
    },
    onError: (err: Error) => toast.error(`Failed to create: ${err.message}`),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/manifests/${id}`),
    onSuccess: () => {
      toast.success('Manifest deleted')
      queryClient.invalidateQueries({ queryKey: ['manifests'] })
      setDeleteManifest(null)
    },
    onError: (err: Error) => toast.error(`Failed to delete: ${err.message}`),
  })

  const manifestByName = useMemo(() => {
    const m = new Map<string, ManifestRead>()
    for (const man of manifests ?? []) {
      m.set(man.name, man)
    }
    return m
  }, [manifests])

  const tableColumns = useMemo<ColumnDef<ManifestRead>[]>(
    () => [
      {
        id: 'title',
        header: 'Manifest',
        accessorFn: (row) => manifestTitle(row),
        cell: ({ row }) => {
          const m = row.original
          return (
            <div className="min-w-0 max-w-[min(100%,24rem)]">
              <Link
                to={`/manifests/${m.id}`}
                className="font-medium text-primary underline-offset-4 hover:underline"
              >
                {manifestTitle(m)}
              </Link>
              {manifestTitle(m) !== m.name ? (
                <div className="truncate font-mono text-xs text-muted-foreground">
                  {m.name}
                </div>
              ) : null}
            </div>
          )
        },
      },
      {
        id: 'catalogs',
        header: 'Catalogs',
        accessorFn: (row) => row.catalog_names.join(', '),
        cell: ({ row }) => (
          <div className="flex max-w-xs flex-wrap gap-1">
            {row.original.catalog_names.length ? (
              row.original.catalog_names.map((c) => (
                <Badge key={c} variant="secondary" className="font-normal">
                  {c}
                </Badge>
              ))
            ) : (
              <span className="text-muted-foreground">—</span>
            )}
          </div>
        ),
      },
      {
        id: 'managed_installs',
        header: 'Managed',
        accessorFn: (row) => row.managed_installs.length,
        cell: ({ row }) => (
          <span className="tabular-nums">
            {row.original.managed_installs.length}
          </span>
        ),
      },
      {
        id: 'optional_installs',
        header: 'Optional',
        accessorFn: (row) => row.optional_installs.length,
        cell: ({ row }) => (
          <span className="tabular-nums">
            {row.original.optional_installs.length}
          </span>
        ),
      },
      {
        id: 'managed_uninstalls',
        header: 'Uninstalls',
        accessorFn: (row) => row.managed_uninstalls.length,
        cell: ({ row }) => (
          <span className="tabular-nums">
            {row.original.managed_uninstalls.length}
          </span>
        ),
      },
      {
        id: 'included_manifest_names',
        header: 'Included',
        accessorFn: (row) => row.included_manifest_names.length,
        cell: ({ row }) => {
          const m = row.original
          if (!m.included_manifest_names.length) {
            return <span className="text-muted-foreground">—</span>
          }
          return (
            <div className="flex max-w-md flex-wrap gap-1">
              {m.included_manifest_names.map((n) => (
                <Badge
                  key={n}
                  variant="outline"
                  className="max-w-full font-normal"
                >
                  <span className="truncate">
                    {manifestTitleForName(manifestByName, n)}
                  </span>
                </Badge>
              ))}
            </div>
          )
        },
      },
      {
        id: 'updated_at',
        header: 'Updated',
        accessorKey: 'updated_at',
        cell: ({ row }) => (
          <span
            suppressHydrationWarning
            className="whitespace-nowrap text-sm text-muted-foreground"
          >
            {formatDateTime(row.original.updated_at)}
          </span>
        ),
      },
      ...(canEditManifests
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
                  onClick={() => setDeleteManifest(row.original)}
                  aria-label={`Delete ${manifestTitle(row.original)}`}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              ),
            } satisfies ColumnDef<ManifestRead>,
          ]
        : []),
    ],
    [canEditManifests, manifestByName],
  )

  const handleCreate = () => {
    const trimmed = name.trim()
    if (!trimmed) return
    createMutation.mutate({
      name: trimmed,
      display_name: displayName.trim() || undefined,
    })
  }

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
        <PageHeading icon={FileText} accent="manifests" title="Manifests" />
        <div className="flex flex-wrap items-center justify-end gap-2">
          <div className="inline-flex items-center rounded-md border bg-muted/30 p-0.5">
            <Button
              type="button"
              variant={view === 'cards' ? 'secondary' : 'ghost'}
              size="sm"
              className="h-8 gap-1.5 px-2.5"
              aria-pressed={view === 'cards'}
              aria-label="Card layout"
              onClick={() => setView('cards')}
            >
              <LayoutGrid className="h-4 w-4" aria-hidden />
              Cards
            </Button>
            <Button
              type="button"
              variant={view === 'table' ? 'secondary' : 'ghost'}
              size="sm"
              className="h-8 gap-1.5 px-2.5"
              aria-pressed={view === 'table'}
              aria-label="Table layout"
              onClick={() => setView('table')}
            >
              <Table2 className="h-4 w-4" aria-hidden />
              Table
            </Button>
          </div>
          <Dialog open={createOpen} onOpenChange={setCreateOpen}>
            {canEditManifests ? (
              <DialogTrigger asChild>
                <Button>
                  <Plus className="h-4 w-4" />
                  New Manifest
                </Button>
              </DialogTrigger>
            ) : null}
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Create Manifest</DialogTitle>
                <DialogDescription>
                  Create a new Munki manifest. You can add catalogs and software
                  after creation.
                </DialogDescription>
              </DialogHeader>
              <div className="grid gap-4 py-4">
                <div className="grid gap-2">
                  <Label htmlFor="manifest-name">Name</Label>
                  <Input
                    id="manifest-name"
                    placeholder="e.g. site_default"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') handleCreate()
                    }}
                  />
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="manifest-display-name">
                    Display Name (optional)
                  </Label>
                  <Input
                    id="manifest-display-name"
                    placeholder="e.g. Default Site Manifest"
                    value={displayName}
                    onChange={(e) => setDisplayName(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') handleCreate()
                    }}
                  />
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
        </div>
      </div>

      {/* Delete Confirmation Dialog */}
      <Dialog
        open={!!deleteManifest}
        onOpenChange={(v) => {
          if (!v) setDeleteManifest(null)
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Manifest</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete &ldquo;
              {deleteManifest ? manifestTitle(deleteManifest) : ''}
              &rdquo;? This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteManifest(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() =>
                deleteManifest && deleteMutation.mutate(deleteManifest.id)
              }
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending ? 'Deleting...' : 'Delete'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {!manifests?.length ? (
        <p className="text-muted-foreground">
          No manifests found. Click &ldquo;New Manifest&rdquo; to create one.
        </p>
      ) : view === 'table' ? (
        <DataTable<ManifestRead, unknown>
          columns={tableColumns}
          data={manifests}
          getRowId={(row) => row.id}
        />
      ) : (
        <div className="grid gap-4 grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
          {manifests.map((manifest) => (
            <Card
              key={manifest.id}
              className={cn(
                'relative h-full overflow-hidden',
                munkiAccents.manifests.manifestGridCard,
              )}
            >
              <Link
                to={`/manifests/${manifest.id}`}
                className="absolute inset-0 z-[1] cursor-pointer rounded-xl outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                aria-label={`Edit manifest ${manifestTitle(manifest)}`}
              />
              <CardHeader className="relative z-[2] pointer-events-none">
                <CardTitle className="flex items-center justify-between">
                  <div className="flex min-w-0 flex-col gap-0.5">
                    <div className="flex items-center gap-3">
                      <FileText
                        className={cn(
                          'h-5 w-5 shrink-0',
                          munkiAccents.manifests.icon,
                        )}
                        aria-hidden
                      />
                      <span className="truncate">
                        {manifestTitle(manifest)}
                      </span>
                    </div>
                    {manifestTitle(manifest) !== manifest.name && (
                      <span className="truncate pl-8 text-sm font-normal text-muted-foreground">
                        {manifest.name}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    {manifest.catalog_names.map((c) => (
                      <Badge key={c} variant="secondary">
                        {c}
                      </Badge>
                    ))}
                    {canEditManifests ? (
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        className="pointer-events-auto h-8 w-8 text-muted-foreground hover:text-destructive"
                        aria-label={`Delete ${manifestTitle(manifest)}`}
                        onClick={() => setDeleteManifest(manifest)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    ) : null}
                  </div>
                </CardTitle>
              </CardHeader>
              <CardContent className="relative z-[2] flex min-h-0 flex-1 flex-col pointer-events-none">
                <div className="flex min-h-0 flex-1 flex-col gap-4">
                  {manifest.managed_installs.length > 0 && (
                    <div>
                      <h4 className="mb-2 text-sm font-medium text-muted-foreground">
                        Managed Installs
                      </h4>
                      <SoftwareNameAvatarCircles
                        names={manifest.managed_installs.map(
                          (n) => parseManifestItemRef(n).baseName,
                        )}
                        maxVisible={MANIFEST_CARD_AVATAR_MAX}
                        interactive={false}
                      />
                    </div>
                  )}

                  {manifest.managed_uninstalls.length > 0 && (
                    <div>
                      <h4 className="mb-2 text-sm font-medium text-muted-foreground">
                        Managed Uninstalls
                      </h4>
                      <SoftwareNameAvatarCircles
                        names={manifest.managed_uninstalls.map(
                          (n) => parseManifestItemRef(n).baseName,
                        )}
                        maxVisible={MANIFEST_CARD_AVATAR_MAX}
                        interactive={false}
                      />
                    </div>
                  )}

                  {manifest.optional_installs.length > 0 && (
                    <div>
                      <h4 className="mb-2 text-sm font-medium text-muted-foreground">
                        Optional Installs
                      </h4>
                      <SoftwareNameAvatarCircles
                        names={manifest.optional_installs.map(
                          (n) => parseManifestItemRef(n).baseName,
                        )}
                        maxVisible={MANIFEST_CARD_AVATAR_MAX}
                        interactive={false}
                      />
                    </div>
                  )}

                  {manifest.included_manifest_names.length > 0 && (
                    <>
                      <Separator />
                      <div>
                        <h4 className="mb-2 text-sm font-medium text-muted-foreground">
                          Included Manifests
                        </h4>
                        <div className="flex flex-wrap gap-1">
                          {manifest.included_manifest_names.map((n) => (
                            <Badge key={n} variant="secondary">
                              {manifestTitleForName(manifestByName, n)}
                            </Badge>
                          ))}
                        </div>
                      </div>
                    </>
                  )}

                  <p
                    suppressHydrationWarning
                    className="mt-auto pt-2 text-xs text-muted-foreground"
                  >
                    Updated {formatDateTime(manifest.updated_at)}
                  </p>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
