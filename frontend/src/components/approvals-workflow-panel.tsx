import {
  closestCenter,
  DndContext,
  type DragEndEvent,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
} from '@dnd-kit/core'
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { GripVertical, Pencil, Plus, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'
import { useAuth } from '@/components/auth-provider'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
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
import { Slider } from '@/components/ui/slider'
import { Switch } from '@/components/ui/switch'
import {
  api,
  type CatalogRead,
  type PromotionChannelRead,
  type WorkflowPreferencesRead,
} from '@/lib/api'
import { PAGE_KEYS } from '@/lib/page-keys'
import { cn } from '@/lib/utils'

type StepDraft = {
  id: string
  source_catalog_id: string
  target_catalog_id: string
  dwell_days: number
}

function newStepDraft(): StepDraft {
  return {
    id: `new-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
    source_catalog_id: '',
    target_catalog_id: '',
    dwell_days: 0,
  }
}

function SortablePromotionStepCard({
  row,
  stepNumber,
  catalogOptions,
  onUpdate,
  onRemove,
}: {
  row: StepDraft
  stepNumber: number
  catalogOptions: CatalogRead[]
  onUpdate: (
    id: string,
    patch: Partial<
      Pick<StepDraft, 'source_catalog_id' | 'target_catalog_id' | 'dwell_days'>
    >,
  ) => void
  onRemove: (id: string) => void
}) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: row.id })

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.55 : 1,
  }

  return (
    <div
      ref={setNodeRef}
      style={style}
      className="rounded-md border bg-card p-3"
    >
      <div className="flex gap-3">
        <button
          type="button"
          className={cn(
            'mt-0.5 h-8 w-7 shrink-0 touch-none rounded-md text-muted-foreground',
            'cursor-grab active:cursor-grabbing hover:bg-muted/80',
            'focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none',
          )}
          aria-label={`Drag to reorder step ${stepNumber}`}
          {...attributes}
          {...listeners}
        >
          <GripVertical className="mx-auto h-4 w-4" aria-hidden />
        </button>
        <div className="grid min-w-0 flex-1 gap-2 sm:grid-cols-2">
          <p className="text-xs text-muted-foreground sm:col-span-2">
            Step {stepNumber}
          </p>
          <div className="space-y-1">
            <Label className="text-xs">From catalog</Label>
            <Select
              value={row.source_catalog_id || '__pick__'}
              onValueChange={(v) =>
                onUpdate(row.id, {
                  source_catalog_id: v === '__pick__' ? '' : v,
                })
              }
            >
              <SelectTrigger>
                <SelectValue placeholder="Source" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__pick__">Select…</SelectItem>
                {catalogOptions.map((c) => (
                  <SelectItem key={c.id} value={c.id}>
                    {c.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label className="text-xs">To catalog</Label>
            <Select
              value={row.target_catalog_id || '__pick__'}
              onValueChange={(v) =>
                onUpdate(row.id, {
                  target_catalog_id: v === '__pick__' ? '' : v,
                })
              }
            >
              <SelectTrigger>
                <SelectValue placeholder="Target" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__pick__">Select…</SelectItem>
                {catalogOptions.map((c) => (
                  <SelectItem key={c.id} value={c.id}>
                    {c.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1 sm:col-span-2">
            <Label className="text-xs">Dwell (days)</Label>
            <Input
              type="number"
              min={0}
              value={row.dwell_days}
              onChange={(e) => {
                const v = Number.parseInt(e.target.value, 10)
                onUpdate(row.id, {
                  dwell_days: Number.isNaN(v) ? 0 : v,
                })
              }}
            />
          </div>
          <div className="sm:col-span-2 flex justify-end">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="text-destructive"
              onClick={() => onRemove(row.id)}
            >
              <Trash2 className="mr-1 h-3.5 w-3.5" aria-hidden />
              Remove step
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}

export function ApprovalsWorkflowPanel() {
  const queryClient = useQueryClient()
  const { canRead, canWrite } = useAuth()
  const canSee = canRead(PAGE_KEYS.autopkgApprovals)
  const canPrefs = canWrite(PAGE_KEYS.autopkgApprovals)
  const canChannels = canWrite(PAGE_KEYS.munkiCatalogs)

  const { data: prefs } = useQuery({
    queryKey: ['workflow-preferences'],
    queryFn: () => api.get<WorkflowPreferencesRead>('/workflow/preferences'),
    enabled: canSee,
  })

  const { data: channels } = useQuery({
    queryKey: ['promotion-channels'],
    queryFn: () => api.get<PromotionChannelRead[]>('/promotion-channels'),
    enabled: canSee,
  })

  const { data: catalogs } = useQuery({
    queryKey: ['catalogs'],
    queryFn: () => api.get<CatalogRead[]>('/catalogs'),
    enabled: canSee,
  })

  const patchPrefs = useMutation({
    mutationFn: (body: Partial<WorkflowPreferencesRead>) =>
      api.patch<WorkflowPreferencesRead>('/workflow/preferences', body),
    onSuccess: () => {
      toast.success('Workflow preferences updated')
      queryClient.invalidateQueries({ queryKey: ['workflow-preferences'] })
    },
    onError: (e: Error) => toast.error(e.message),
  })

  const patchChannel = useMutation({
    mutationFn: ({
      id,
      steps,
    }: {
      id: string
      steps: {
        step_order: number
        source_catalog_id: string
        target_catalog_id: string
        dwell_days: number
      }[]
    }) =>
      api.patch<PromotionChannelRead>(`/promotion-channels/${id}`, { steps }),
    onSuccess: () => {
      toast.success('Promotion channel updated')
      queryClient.invalidateQueries({ queryKey: ['promotion-channels'] })
    },
    onError: (e: Error) => toast.error(e.message),
  })

  const createChannel = useMutation({
    mutationFn: (body: { name: string; description?: string | null }) =>
      api.post<PromotionChannelRead>('/promotion-channels', body),
    onSuccess: () => {
      toast.success('Promotion channel created')
      queryClient.invalidateQueries({ queryKey: ['promotion-channels'] })
      queryClient.invalidateQueries({ queryKey: ['workflow-preferences'] })
    },
    onError: (e: Error) => toast.error(e.message),
  })

  const deleteChannel = useMutation({
    mutationFn: (id: string) => api.delete(`/promotion-channels/${id}`),
    onSuccess: () => {
      toast.success('Promotion channel removed')
      queryClient.invalidateQueries({ queryKey: ['promotion-channels'] })
      queryClient.invalidateQueries({ queryKey: ['workflow-preferences'] })
      queryClient.invalidateQueries({ queryKey: ['autopkg-recipes'] })
    },
    onError: (e: Error) => toast.error(e.message),
  })

  const [editChannel, setEditChannel] = useState<PromotionChannelRead | null>(
    null,
  )
  const [addChannelOpen, setAddChannelOpen] = useState(false)
  const [newChannelName, setNewChannelName] = useState('')
  const [newChannelDescription, setNewChannelDescription] = useState('')
  const [stepDrafts, setStepDrafts] = useState<StepDraft[]>([])
  const [shardDays, setShardDays] = useState(4)

  useEffect(() => {
    if (prefs?.production_shard_days != null) {
      setShardDays(prefs.production_shard_days)
    }
  }, [prefs?.production_shard_days])

  const stepSensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    }),
  )

  function handleStepsDragEnd(event: DragEndEvent) {
    const { active, over } = event
    if (!over || active.id === over.id) return
    setStepDrafts((items) => {
      const oldIndex = items.findIndex((x) => x.id === active.id)
      const newIndex = items.findIndex((x) => x.id === over.id)
      if (oldIndex === -1 || newIndex === -1) return items
      return arrayMove(items, oldIndex, newIndex)
    })
  }

  useEffect(() => {
    if (!editChannel) {
      setStepDrafts([])
      return
    }
    setStepDrafts(
      [...editChannel.steps]
        .sort((a, b) => a.step_order - b.step_order)
        .map((s) => ({
          id: s.id,
          source_catalog_id: s.source_catalog_id,
          target_catalog_id: s.target_catalog_id,
          dwell_days: s.dwell_days,
        })),
    )
  }, [editChannel])

  if (!canSee) return null

  const catalogOptions = catalogs ?? []

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Approval workflow</CardTitle>
          <CardDescription>
            Imports from overrides with <strong>Auto Promote</strong> off stay
            in the catalog marked <strong>Quarantine</strong> until approved
            here. Designate that catalog on{' '}
            <Link
              to="/catalogs"
              className="text-primary underline-offset-4 hover:underline"
            >
              Catalogs
            </Link>
            . Toggle <strong>Auto Promote</strong> per recipe on{' '}
            <Link
              to="/autopkg/recipes"
              className="text-primary underline-offset-4 hover:underline"
            >
              Recipes
            </Link>
            .
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2 max-w-md">
            <Label htmlFor="default-promotion-channel">
              Default promotion channel
            </Label>
            <p className="text-xs text-muted-foreground">
              Used when a recipe does not set its own channel. Channels define
              timed moves between catalogs (scheduler or schedule webhook).
            </p>
            <Select
              value={prefs?.default_promotion_channel_id ?? '__none__'}
              onValueChange={(v) => {
                if (!canPrefs) return
                patchPrefs.mutate({
                  default_promotion_channel_id: v === '__none__' ? null : v,
                })
              }}
              disabled={!canPrefs || patchPrefs.isPending}
            >
              <SelectTrigger id="default-promotion-channel">
                <SelectValue placeholder="None" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__none__">None</SelectItem>
                {(channels ?? []).map((ch) => (
                  <SelectItem key={ch.id} value={ch.id}>
                    {ch.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm font-medium">Channels</p>
              {canChannels ? (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setNewChannelName('')
                    setNewChannelDescription('')
                    setAddChannelOpen(true)
                  }}
                >
                  <Plus className="mr-1 h-3.5 w-3.5" aria-hidden />
                  Add channel
                </Button>
              ) : null}
            </div>
            <ul className="divide-y rounded-md border">
              {(channels ?? []).length === 0 ? (
                <li className="px-3 py-3 text-sm text-muted-foreground">
                  No promotion channels yet.
                  {canChannels ? ' Click Add channel to create one.' : ''}
                </li>
              ) : (
                (channels ?? []).map((ch) => (
                  <li
                    key={ch.id}
                    className="flex flex-wrap items-center justify-between gap-2 px-3 py-2"
                  >
                    <div>
                      <span className="font-medium">{ch.name}</span>
                      <span className="ml-2 text-xs text-muted-foreground">
                        {ch.steps.length} step
                        {ch.steps.length === 1 ? '' : 's'}
                      </span>
                    </div>
                    {canChannels ? (
                      <div className="flex flex-wrap items-center gap-2">
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={() => setEditChannel(ch)}
                        >
                          <Pencil className="mr-1 h-3.5 w-3.5" aria-hidden />
                          Edit steps
                        </Button>
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          className="text-destructive hover:text-destructive"
                          disabled={deleteChannel.isPending}
                          onClick={() => {
                            if (
                              !window.confirm(
                                `Remove promotion channel “${ch.name}”? Recipes using it will fall back to the workflow default. This cannot be undone.`,
                              )
                            ) {
                              return
                            }
                            if (editChannel?.id === ch.id) setEditChannel(null)
                            deleteChannel.mutate(ch.id)
                          }}
                        >
                          <Trash2 className="mr-1 h-3.5 w-3.5" aria-hidden />
                          Remove
                        </Button>
                      </div>
                    ) : null}
                  </li>
                ))
              )}
            </ul>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Production shard rollout</CardTitle>
          <CardDescription>
            Separate from catalog promotion. After a version lands in a{' '}
            <strong>production</strong> catalog, the scheduler writes{' '}
            <code className="text-xs">installable_condition</code> daily so
            clients roll out by device shard. Manage per-version status on the{' '}
            <Link
              to="/software"
              className="text-primary underline-offset-4 hover:underline"
            >
              Software
            </Link>{' '}
            detail page.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4 max-w-md">
          <div className="flex items-center gap-2">
            <Switch
              id="production-shard-enabled"
              checked={prefs?.production_shard_enabled ?? true}
              disabled={!canPrefs || patchPrefs.isPending}
              onCheckedChange={(v) => {
                if (!canPrefs) return
                patchPrefs.mutate({ production_shard_enabled: v })
              }}
            />
            <Label htmlFor="production-shard-enabled" className="font-normal">
              Enable automatic shard tick
            </Label>
          </div>
          <div className="space-y-3">
            <div className="flex items-center justify-between gap-3">
              <Label htmlFor="production-shard-days">
                Rollout days (to 100%)
              </Label>
              <span className="font-mono text-sm tabular-nums">
                {shardDays} days
              </span>
            </div>
            <p className="text-xs text-muted-foreground">
              Days until all devices are eligible (e.g. 4 → 25% per day).
            </p>
            <Slider
              id="production-shard-days"
              min={1}
              max={30}
              step={1}
              value={[shardDays]}
              disabled={!canPrefs || patchPrefs.isPending}
              onValueChange={(v) => setShardDays(v[0] ?? 4)}
              onValueCommit={(v) => {
                if (!canPrefs) return
                const n = v[0] ?? 4
                setShardDays(n)
                patchPrefs.mutate({ production_shard_days: n })
              }}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="net-new-shard-policy">
              Net-new software policy
            </Label>
            <p className="text-xs text-muted-foreground">
              First-ever production deploy for a title — avoids catalog warnings
              on high-shard machines when the title is already in manifests.
            </p>
            <Select
              value={prefs?.net_new_shard_policy ?? 'skip_until_approved'}
              onValueChange={(v) => {
                if (!canPrefs) return
                patchPrefs.mutate({ net_new_shard_policy: v })
              }}
              disabled={!canPrefs || patchPrefs.isPending}
            >
              <SelectTrigger id="net-new-shard-policy">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="skip_until_approved">
                  Require approval before rollout (recommended)
                </SelectItem>
                <SelectItem value="immediate_full">
                  Skip sharding (100% immediately)
                </SelectItem>
                <SelectItem value="same_as_upgrades">
                  Same as upgrades (auto-shard)
                </SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      <Dialog
        open={addChannelOpen}
        onOpenChange={(v) => {
          setAddChannelOpen(v)
          if (!v) {
            setNewChannelName('')
            setNewChannelDescription('')
          }
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Add promotion channel</DialogTitle>
            <DialogDescription>
              Create a named channel, then add catalog steps with Edit steps.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-2">
            <div className="space-y-2">
              <Label htmlFor="new-channel-name">Name</Label>
              <Input
                id="new-channel-name"
                placeholder="e.g. staging"
                value={newChannelName}
                onChange={(e) => setNewChannelName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && newChannelName.trim()) {
                    e.preventDefault()
                    createChannel.mutate(
                      {
                        name: newChannelName.trim(),
                        description: newChannelDescription.trim() || null,
                      },
                      {
                        onSuccess: () => {
                          setAddChannelOpen(false)
                          setNewChannelName('')
                          setNewChannelDescription('')
                        },
                      },
                    )
                  }
                }}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="new-channel-description">
                Description (optional)
              </Label>
              <Input
                id="new-channel-description"
                placeholder="Short note for operators"
                value={newChannelDescription}
                onChange={(e) => setNewChannelDescription(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setAddChannelOpen(false)}
            >
              Cancel
            </Button>
            <Button
              type="button"
              disabled={!newChannelName.trim() || createChannel.isPending}
              onClick={() =>
                createChannel.mutate(
                  {
                    name: newChannelName.trim(),
                    description: newChannelDescription.trim() || null,
                  },
                  {
                    onSuccess: () => {
                      setAddChannelOpen(false)
                      setNewChannelName('')
                      setNewChannelDescription('')
                    },
                  },
                )
              }
            >
              {createChannel.isPending ? 'Creating…' : 'Create'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={!!editChannel}
        onOpenChange={(v) => {
          if (!v) setEditChannel(null)
        }}
      >
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Steps: {editChannel?.name}</DialogTitle>
            <DialogDescription>
              Drag steps by the grip to set promotion order (top runs first).
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <DndContext
              sensors={stepSensors}
              collisionDetection={closestCenter}
              onDragEnd={handleStepsDragEnd}
            >
              <SortableContext
                items={stepDrafts.map((s) => s.id)}
                strategy={verticalListSortingStrategy}
              >
                {stepDrafts.map((row, idx) => (
                  <SortablePromotionStepCard
                    key={row.id}
                    row={row}
                    stepNumber={idx + 1}
                    catalogOptions={catalogOptions}
                    onUpdate={(id, patch) =>
                      setStepDrafts((prev) =>
                        prev.map((r) => (r.id === id ? { ...r, ...patch } : r)),
                      )
                    }
                    onRemove={(id) =>
                      setStepDrafts((prev) => prev.filter((r) => r.id !== id))
                    }
                  />
                ))}
              </SortableContext>
            </DndContext>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="w-full"
              onClick={() => setStepDrafts((prev) => [...prev, newStepDraft()])}
            >
              <Plus className="mr-1 h-3.5 w-3.5" aria-hidden />
              Add step
            </Button>
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setEditChannel(null)}
            >
              Cancel
            </Button>
            <Button
              type="button"
              disabled={
                !editChannel ||
                patchChannel.isPending ||
                stepDrafts.some(
                  (s) => !s.source_catalog_id || !s.target_catalog_id,
                )
              }
              onClick={() => {
                if (!editChannel) return
                patchChannel.mutate(
                  {
                    id: editChannel.id,
                    steps: stepDrafts.map((s, i) => ({
                      step_order: i,
                      source_catalog_id: s.source_catalog_id,
                      target_catalog_id: s.target_catalog_id,
                      dwell_days: s.dwell_days,
                    })),
                  },
                  { onSuccess: () => setEditChannel(null) },
                )
              }}
            >
              Save steps
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
