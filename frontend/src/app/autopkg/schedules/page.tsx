import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  CalendarClock,
  Loader2,
  Pencil,
  Plus,
  Save,
  Search,
  Trash2,
} from 'lucide-react'
import { useId, useState } from 'react'
import { toast } from 'sonner'
import { useAuth } from '@/components/auth-provider'
import { PageHeading } from '@/components/page-heading'
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { useDocumentTitle } from '@/hooks/use-document-title'
import {
  type AutoPkgRecipeRead,
  type AutoPkgScheduleRead,
  api,
} from '@/lib/api'
import { fetchEnabledAutopkgRecipes } from '@/lib/autopkg-recipes-api'
import { canTriggerRunRecipe } from '@/lib/autopkg-run'
import { formatDateTime } from '@/lib/format'
import { PAGE_KEYS } from '@/lib/page-keys'
import { cn } from '@/lib/utils'

function emptyForm(): {
  name: string
  cron_expression: string
  timezone: string
  useRecipeSubset: boolean
  selectedRecipes: Set<string>
  runner: 'github' | 'local'
  enabled: boolean
} {
  return {
    name: '',
    cron_expression: '0 9 * * *',
    timezone: 'UTC',
    useRecipeSubset: false,
    selectedRecipes: new Set<string>(),
    runner: 'github',
    enabled: true,
  }
}

export default function AutoPkgSchedulesPage() {
  useDocumentTitle('AutoPkg', 'Schedules')
  const { canWrite } = useAuth()
  const canEdit = canWrite(PAGE_KEYS.autopkgRuns)
  const queryClient = useQueryClient()
  const selectAllCheckboxId = useId()

  const [dialogOpen, setDialogOpen] = useState(false)
  const [editing, setEditing] = useState<AutoPkgScheduleRead | null>(null)
  const [form, setForm] = useState(emptyForm)
  const [recipeSearch, setRecipeSearch] = useState('')

  const { data: schedules, isLoading } = useQuery({
    queryKey: ['autopkg-schedules'],
    queryFn: () => api.get<AutoPkgScheduleRead[]>('/autopkg/schedules'),
  })

  const { data: recipes } = useQuery({
    queryKey: ['autopkg-recipes-enabled'],
    queryFn: () => fetchEnabledAutopkgRecipes(),
    enabled: dialogOpen,
  })

  const saveMutation = useMutation({
    mutationFn: async () => {
      let recipeNames: string[] | null = null
      if (form.useRecipeSubset) {
        const runnable = [...form.selectedRecipes].filter((n) => {
          const r = recipes?.find((x) => x.name === n)
          return r && canTriggerRunRecipe(r)
        })
        if (runnable.length === 0) {
          throw new Error(
            'Select at least one runnable recipe, or turn off “specific recipes”.',
          )
        }
        recipeNames = runnable
      }
      const body = {
        name: form.name.trim(),
        cron_expression: form.cron_expression.trim(),
        timezone: form.timezone.trim(),
        recipe_names: recipeNames,
        runner: form.runner,
        enabled: form.enabled,
      }
      if (editing) {
        return await api.patch<AutoPkgScheduleRead>(
          `/autopkg/schedules/${editing.id}`,
          body,
        )
      }
      return await api.post<AutoPkgScheduleRead>('/autopkg/schedules', body)
    },
    onSuccess: () => {
      toast.success(editing ? 'Schedule updated' : 'Schedule created')
      queryClient.invalidateQueries({ queryKey: ['autopkg-schedules'] })
      setDialogOpen(false)
      setEditing(null)
      setForm(emptyForm())
      setRecipeSearch('')
    },
    onError: (err: Error) => toast.error(err.message),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/autopkg/schedules/${id}`),
    onSuccess: () => {
      toast.success('Schedule deleted')
      queryClient.invalidateQueries({ queryKey: ['autopkg-schedules'] })
    },
    onError: (err: Error) => toast.error(err.message),
  })

  const openCreate = () => {
    setEditing(null)
    setForm(emptyForm())
    setRecipeSearch('')
    setDialogOpen(true)
  }

  const openEdit = (sch: AutoPkgScheduleRead) => {
    setEditing(sch)
    const hasSubset = Boolean(sch.recipe_names && sch.recipe_names.length > 0)
    setForm({
      name: sch.name,
      cron_expression: sch.cron_expression,
      timezone: sch.timezone,
      useRecipeSubset: hasSubset,
      selectedRecipes: new Set(sch.recipe_names ?? []),
      runner: sch.runner_type === 'local' ? 'local' : 'github',
      enabled: sch.enabled,
    })
    setRecipeSearch('')
    setDialogOpen(true)
  }

  const filteredRecipes = (recipes ?? []).filter((r) =>
    recipeSearch
      ? r.name.toLowerCase().includes(recipeSearch.toLowerCase()) ||
        r.identifier.toLowerCase().includes(recipeSearch.toLowerCase())
      : true,
  )

  const runnableInFilter = filteredRecipes.filter(canTriggerRunRecipe)

  return (
    <div className="flex h-[calc(100vh-3rem)] min-w-0 w-full max-w-full flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <PageHeading
          icon={CalendarClock}
          accent="autopkg"
          title="AutoPkg Schedules"
        />
        {canEdit ? (
          <Button type="button" onClick={openCreate}>
            <Plus className="h-4 w-4" />
            Add schedule
          </Button>
        ) : null}
      </div>

      <p className="max-w-2xl text-sm text-muted-foreground">
        Cron schedules run in the Munki Manager API process (every minute). Use
        GitHub Actions for cloud builds or Local Mac for your own runner daemon.
        Set <code className="text-xs">SCHEDULER_ENABLED=false</code> on all but
        one replica if you run multiple API instances.
      </p>

      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Cron</TableHead>
              <TableHead>Timezone</TableHead>
              <TableHead>Runner</TableHead>
              <TableHead>Recipes</TableHead>
              <TableHead>Next run</TableHead>
              <TableHead>Enabled</TableHead>
              {canEdit ? <TableHead className="w-[100px]" /> : null}
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={canEdit ? 8 : 7}>
                  <Loader2 className="mx-auto h-6 w-6 animate-spin text-muted-foreground" />
                </TableCell>
              </TableRow>
            ) : !schedules?.length ? (
              <TableRow>
                <TableCell
                  colSpan={canEdit ? 8 : 7}
                  className="text-center text-muted-foreground"
                >
                  No schedules yet.
                </TableCell>
              </TableRow>
            ) : (
              schedules.map((sch) => (
                <TableRow key={sch.id}>
                  <TableCell className="font-medium">{sch.name}</TableCell>
                  <TableCell>
                    <code className="text-xs">{sch.cron_expression}</code>
                  </TableCell>
                  <TableCell className="text-sm">{sch.timezone}</TableCell>
                  <TableCell>
                    <Badge variant="secondary">
                      {sch.runner_type === 'local' ? 'Local Mac' : 'GitHub'}
                    </Badge>
                  </TableCell>
                  <TableCell className="max-w-[200px] truncate text-sm">
                    {sch.recipe_names?.length
                      ? `${sch.recipe_names.length} selected`
                      : 'All enabled'}
                  </TableCell>
                  <TableCell className="text-sm">
                    {sch.next_run_at ? (
                      <span suppressHydrationWarning>
                        {formatDateTime(sch.next_run_at)}
                      </span>
                    ) : (
                      '—'
                    )}
                  </TableCell>
                  <TableCell>
                    <Badge variant={sch.enabled ? 'default' : 'outline'}>
                      {sch.enabled ? 'on' : 'off'}
                    </Badge>
                  </TableCell>
                  {canEdit ? (
                    <TableCell className="text-right">
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        aria-label={`Edit ${sch.name}`}
                        onClick={() => openEdit(sch)}
                      >
                        <Pencil className="h-4 w-4" />
                      </Button>
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        aria-label={`Delete ${sch.name}`}
                        onClick={() => {
                          if (
                            typeof window !== 'undefined' &&
                            !window.confirm(`Delete schedule “${sch.name}”?`)
                          ) {
                            return
                          }
                          deleteMutation.mutate(sch.id)
                        }}
                      >
                        <Trash2 className="h-4 w-4 text-destructive" />
                      </Button>
                    </TableCell>
                  ) : null}
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>
              {editing ? 'Edit schedule' : 'New schedule'}
            </DialogTitle>
            <DialogDescription>
              Standard five-field cron (minute hour day month weekday). Empty
              recipe selection means all enabled overrides.
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-3">
            <div className="grid gap-2">
              <Label htmlFor="sch-name">Name</Label>
              <Input
                id="sch-name"
                value={form.name}
                onChange={(e) =>
                  setForm((f) => ({ ...f, name: e.target.value }))
                }
                placeholder="Nightly imports"
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="sch-cron">Cron</Label>
              <Input
                id="sch-cron"
                value={form.cron_expression}
                onChange={(e) =>
                  setForm((f) => ({ ...f, cron_expression: e.target.value }))
                }
                placeholder="0 9 * * *"
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="sch-tz">Timezone (IANA)</Label>
              <Input
                id="sch-tz"
                value={form.timezone}
                onChange={(e) =>
                  setForm((f) => ({ ...f, timezone: e.target.value }))
                }
                placeholder="UTC"
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="sch-runner">Runner</Label>
              <Select
                value={form.runner}
                onValueChange={(v) =>
                  setForm((f) => ({
                    ...f,
                    runner: v as 'github' | 'local',
                  }))
                }
              >
                <SelectTrigger id="sch-runner">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="github">GitHub Actions</SelectItem>
                  <SelectItem value="local">Local Mac (daemon)</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-center gap-2">
              <Checkbox
                id="sch-enabled"
                checked={form.enabled}
                onCheckedChange={(c) =>
                  setForm((f) => ({ ...f, enabled: Boolean(c) }))
                }
              />
              <Label htmlFor="sch-enabled" className="font-normal">
                Enabled
              </Label>
            </div>

            <div className="flex items-center gap-2">
              <Checkbox
                id="sch-subset"
                checked={form.useRecipeSubset}
                onCheckedChange={(c) =>
                  setForm((f) => ({
                    ...f,
                    useRecipeSubset: Boolean(c),
                  }))
                }
              />
              <Label htmlFor="sch-subset" className="font-normal">
                Run only specific recipes
              </Label>
            </div>

            {form.useRecipeSubset ? (
              <div className="space-y-2 rounded-md border p-3">
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    placeholder="Filter recipes..."
                    value={recipeSearch}
                    onChange={(e) => setRecipeSearch(e.target.value)}
                    className="pl-9"
                  />
                </div>
                <div className="flex items-center justify-between text-sm">
                  <div className="flex items-center gap-2">
                    <Checkbox
                      id={selectAllCheckboxId}
                      checked={
                        runnableInFilter.length > 0 &&
                        runnableInFilter.every((r) =>
                          form.selectedRecipes.has(r.name),
                        )
                      }
                      disabled={runnableInFilter.length === 0}
                      onCheckedChange={(checked) => {
                        if (runnableInFilter.length === 0) return
                        if (checked === true) {
                          setForm((f) => ({
                            ...f,
                            selectedRecipes: new Set(
                              runnableInFilter.map((r) => r.name),
                            ),
                          }))
                        } else {
                          setForm((f) => ({ ...f, selectedRecipes: new Set() }))
                        }
                      }}
                    />
                    <label
                      htmlFor={selectAllCheckboxId}
                      className={cn(
                        runnableInFilter.length > 0
                          ? 'cursor-pointer'
                          : 'cursor-not-allowed opacity-60',
                      )}
                    >
                      Select all runnable ({runnableInFilter.length})
                    </label>
                  </div>
                </div>
                <div className="max-h-[220px] space-y-1 overflow-y-auto">
                  {filteredRecipes.map((recipe) => {
                    const canRun = canTriggerRunRecipe(recipe)
                    const rowCheckboxId = `schedule-recipe-${recipe.id}`
                    return (
                      <div
                        key={recipe.id}
                        className={cn(
                          'flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm',
                          canRun
                            ? 'hover:bg-muted/60'
                            : 'cursor-not-allowed opacity-60',
                        )}
                      >
                        <Checkbox
                          id={rowCheckboxId}
                          checked={form.selectedRecipes.has(recipe.name)}
                          disabled={!canRun}
                          onCheckedChange={(checked) => {
                            if (!canRun) return
                            setForm((f) => {
                              const next = new Set(f.selectedRecipes)
                              if (checked === true) next.add(recipe.name)
                              else next.delete(recipe.name)
                              return { ...f, selectedRecipes: next }
                            })
                          }}
                        />
                        {canRun ? (
                          <label
                            htmlFor={rowCheckboxId}
                            className="flex-1 cursor-pointer truncate"
                          >
                            {recipe.name}
                          </label>
                        ) : (
                          <span className="flex-1 truncate">{recipe.name}</span>
                        )}
                        {!canRun ? (
                          <Badge variant="secondary" className="text-xs">
                            trust blocked
                          </Badge>
                        ) : null}
                      </div>
                    )
                  })}
                </div>
              </div>
            ) : null}
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setDialogOpen(false)}
            >
              Cancel
            </Button>
            <Button
              type="button"
              disabled={saveMutation.isPending || !form.name.trim()}
              onClick={() => saveMutation.mutate()}
            >
              {saveMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : editing ? (
                <>
                  <Save className="h-4 w-4" aria-hidden />
                  Save
                </>
              ) : (
                <>
                  <Plus className="h-4 w-4" aria-hidden />
                  Create
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
