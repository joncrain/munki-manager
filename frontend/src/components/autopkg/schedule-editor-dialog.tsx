import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2, Plus, Save, Search } from 'lucide-react'
import { useEffect, useId, useState } from 'react'
import { toast } from 'sonner'
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
  type AutoPkgRecipeRead,
  type AutoPkgScheduleRead,
  api,
} from '@/lib/api'
import { fetchEnabledAutopkgRecipes } from '@/lib/autopkg-recipes-api'
import { canTriggerRunRecipe } from '@/lib/autopkg-run'
import { formatCronExpression } from '@/lib/cron-expression'
import { cn } from '@/lib/utils'

export function emptyScheduleForm(): {
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

export function scheduleToForm(sch: AutoPkgScheduleRead) {
  const hasSubset = Boolean(sch.recipe_names && sch.recipe_names.length > 0)
  return {
    name: sch.name,
    cron_expression: sch.cron_expression,
    timezone: sch.timezone,
    useRecipeSubset: hasSubset,
    selectedRecipes: new Set(sch.recipe_names ?? []),
    runner:
      sch.runner_type === 'local' ? ('local' as const) : ('github' as const),
    enabled: sch.enabled,
  }
}

export function AutopkgScheduleEditorDialog({
  open,
  onOpenChange,
  editing,
  canEdit,
  onSaved,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  editing: AutoPkgScheduleRead | null
  canEdit: boolean
  onSaved?: () => void
}) {
  const queryClient = useQueryClient()
  const selectAllCheckboxId = useId()
  const [form, setForm] = useState(emptyScheduleForm)
  const [recipeSearch, setRecipeSearch] = useState('')

  useEffect(() => {
    if (!open) return
    setForm(editing ? scheduleToForm(editing) : emptyScheduleForm())
    setRecipeSearch('')
  }, [open, editing])

  const { data: recipes } = useQuery({
    queryKey: ['autopkg-recipes-enabled'],
    queryFn: () => fetchEnabledAutopkgRecipes(),
    enabled: open,
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
      onOpenChange(false)
      onSaved?.()
    },
    onError: (err: Error) => toast.error(err.message),
  })

  const filteredRecipes = (recipes ?? []).filter((r) =>
    recipeSearch
      ? r.name.toLowerCase().includes(recipeSearch.toLowerCase()) ||
        r.identifier.toLowerCase().includes(recipeSearch.toLowerCase())
      : true,
  )

  const runnableInFilter = filteredRecipes.filter(canTriggerRunRecipe)

  const cronPreview = formatCronExpression(form.cron_expression)

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) {
          setForm(emptyScheduleForm())
          setRecipeSearch('')
        }
        onOpenChange(next)
      }}
    >
      <DialogContent className="flex max-h-[90dvh] flex-col gap-0 overflow-hidden p-0 sm:max-h-[85vh] sm:max-w-lg">
        <DialogHeader className="shrink-0 border-b px-6 pt-6 pr-14 pb-4">
          <DialogTitle>
            {editing ? 'Edit schedule' : 'New schedule'}
          </DialogTitle>
          <DialogDescription>
            Standard five-field cron (minute hour day month weekday). Empty
            recipe selection means all enabled overrides.
          </DialogDescription>
        </DialogHeader>

        <div className="grid min-h-0 flex-1 gap-3 overflow-y-auto px-6 py-4">
          <div className="grid gap-2">
            <Label htmlFor="sch-name">Name</Label>
            <Input
              id="sch-name"
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              placeholder="Nightly imports"
              disabled={!canEdit}
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
              disabled={!canEdit}
            />
            {cronPreview && cronPreview !== form.cron_expression.trim() ? (
              <p className="text-xs text-muted-foreground">{cronPreview}</p>
            ) : null}
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
              disabled={!canEdit}
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
              disabled={!canEdit}
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
              disabled={!canEdit}
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
              disabled={!canEdit}
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
                  disabled={!canEdit}
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
                    disabled={!canEdit || runnableInFilter.length === 0}
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
                      runnableInFilter.length > 0 && canEdit
                        ? 'cursor-pointer'
                        : 'cursor-not-allowed opacity-60',
                    )}
                  >
                    Select all runnable ({runnableInFilter.length})
                  </label>
                </div>
              </div>
              <div className="max-h-[220px] space-y-1 overflow-y-auto">
                {filteredRecipes.map((recipe) => (
                  <ScheduleRecipeRow
                    key={recipe.id}
                    recipe={recipe}
                    checked={form.selectedRecipes.has(recipe.name)}
                    canEdit={canEdit}
                    onCheckedChange={(checked) => {
                      if (!canTriggerRunRecipe(recipe)) return
                      setForm((f) => {
                        const next = new Set(f.selectedRecipes)
                        if (checked) next.add(recipe.name)
                        else next.delete(recipe.name)
                        return { ...f, selectedRecipes: next }
                      })
                    }}
                  />
                ))}
              </div>
            </div>
          ) : null}
        </div>

        <DialogFooter className="shrink-0 gap-2 border-t bg-background px-6 py-4 sm:rounded-b-lg">
          <Button
            type="button"
            variant="outline"
            onClick={() => onOpenChange(false)}
            className="w-full sm:w-auto"
          >
            {canEdit ? 'Cancel' : 'Close'}
          </Button>
          {canEdit ? (
            <Button
              type="button"
              disabled={saveMutation.isPending || !form.name.trim()}
              onClick={() => saveMutation.mutate()}
              className="w-full sm:w-auto"
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
          ) : null}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function ScheduleRecipeRow({
  recipe,
  checked,
  canEdit,
  onCheckedChange,
}: {
  recipe: AutoPkgRecipeRead
  checked: boolean
  canEdit: boolean
  onCheckedChange: (checked: boolean) => void
}) {
  const canRun = canTriggerRunRecipe(recipe)
  const rowCheckboxId = `schedule-recipe-${recipe.id}`

  return (
    <div
      className={cn(
        'flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm',
        canRun ? 'hover:bg-muted/60' : 'cursor-not-allowed opacity-60',
      )}
    >
      <Checkbox
        id={rowCheckboxId}
        checked={checked}
        disabled={!canRun || !canEdit}
        onCheckedChange={(c) => onCheckedChange(c === true)}
      />
      {canRun ? (
        <label
          htmlFor={rowCheckboxId}
          className={cn('flex-1 truncate', canEdit && 'cursor-pointer')}
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
}
