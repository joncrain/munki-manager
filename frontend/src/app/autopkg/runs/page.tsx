import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { ColumnDef } from '@tanstack/react-table'
import {
  ChevronDown,
  ChevronRight,
  ExternalLink,
  Loader2,
  Play,
  Search,
  X,
} from 'lucide-react'
import { parseAsInteger, parseAsString, useQueryState } from 'nuqs'
import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { useAuth } from '@/components/auth-provider'
import { DataTable } from '@/components/data-table'
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
  DialogTrigger,
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
import { useDocumentTitle } from '@/hooks/use-document-title'
import {
  type AutoPkgRecipeRead,
  type AutoPkgRunRead,
  api,
  type PaginatedResponse,
  type UiSettingsRead,
} from '@/lib/api'
import { fetchEnabledAutopkgRecipes } from '@/lib/autopkg-recipes-api'
import {
  canTriggerRunRecipe,
  RUNNER_LOCAL_DELIVERY_KEY,
  RUNNER_STORAGE_KEY,
  TrustVerifyFailureDialog,
  toastLocalRunRegistered,
  type VerifyTrustForRunResponse,
  verifyTrustBeforeRun,
} from '@/lib/autopkg-run'
import { formatDateTime } from '@/lib/format'
import { PAGE_KEYS } from '@/lib/page-keys'

const STATUS_OPTIONS = [
  'pending',
  'running',
  'completed',
  'failed',
  'cancelled',
]

function lastRecipeRunLooksOk(status: string): boolean {
  return ['success', 'imported', 'no_change'].includes(status)
}

const statusVariant = (status: string) => {
  switch (status) {
    case 'completed':
      return 'default' as const
    case 'failed':
      return 'destructive' as const
    case 'running':
      return 'secondary' as const
    default:
      return 'outline' as const
  }
}

export default function AutoPkgRunsPage() {
  useDocumentTitle('AutoPkg', 'Runs')
  const { canWrite } = useAuth()
  const canTriggerRuns = canWrite(PAGE_KEYS.autopkgRuns)

  const [trustVerifyIssue, setTrustVerifyIssue] = useState<null | {
    runner: 'github' | 'local'
    verify: VerifyTrustForRunResponse
  }>(null)
  const [trustVerifying, setTrustVerifying] = useState(false)
  const [trustContinuePending, setTrustContinuePending] = useState(false)

  const [page, setPage] = useQueryState('page', parseAsInteger.withDefault(1))
  const [pageSize, setPageSize] = useQueryState(
    'pageSize',
    parseAsInteger.withDefault(20),
  )
  const [status, setStatus] = useQueryState(
    'status',
    parseAsString.withDefault(''),
  )
  const [resultsRunId, setResultsRunId] = useState<string | null>(null)
  const queryClient = useQueryClient()

  const { data: resultsRun, isLoading: resultsRunLoading } = useQuery({
    queryKey: ['autopkg-run', resultsRunId],
    queryFn: () => api.get<AutoPkgRunRead>(`/autopkg/runs/${resultsRunId!}`),
    enabled: !!resultsRunId,
  })

  const { data, isLoading } = useQuery({
    queryKey: ['autopkg-runs', page, pageSize, status],
    queryFn: () => {
      const params = new URLSearchParams()
      params.set('page', String(page))
      params.set('page_size', String(pageSize))
      if (status) params.set('status', status)
      return api.get<PaginatedResponse<AutoPkgRunRead>>(
        `/autopkg/runs?${params.toString()}`,
      )
    },
  })

  const triggerMutation = useMutation({
    mutationFn: (args: {
      recipeNames: string[] | null
      runner: 'github' | 'local'
    }) =>
      api.post<AutoPkgRunRead>('/autopkg/runs', {
        recipe_names: args.recipeNames,
        runner: args.runner,
      }),
    onSuccess: (run) => {
      if (run.runner_type === 'local') {
        toastLocalRunRegistered(run)
      } else {
        toast.success('AutoPkg run triggered on GitHub Actions', {
          description: `Run ID: ${run.id}`,
          duration: 15_000,
        })
      }
      queryClient.invalidateQueries({ queryKey: ['autopkg-runs'] })
      queryClient.invalidateQueries({ queryKey: ['autopkg-recipes'] })
      queryClient.invalidateQueries({ queryKey: ['autopkg-recipes-enabled'] })
    },
    onError: (err: Error) =>
      toast.error(`Failed to trigger run: ${err.message}`),
  })

  const onTriggerRunWithTrust = async (
    recipeNames: string[] | null,
    runner: 'github' | 'local',
  ) => {
    const toastId = toast.loading('Verifying trust with GitHub…')
    setTrustVerifying(true)
    try {
      const res = await verifyTrustBeforeRun(recipeNames)
      if (res.rate_limited && res.results.length === 0) {
        toast.error('GitHub rate limit while verifying trust. Try again later.')
        return
      }
      const failed = res.results.filter((r) => r.status !== 'verified')
      await queryClient.invalidateQueries({ queryKey: ['autopkg-recipes'] })
      await queryClient.invalidateQueries({
        queryKey: ['autopkg-recipes-enabled'],
      })
      await queryClient.invalidateQueries({
        queryKey: ['pending-trust-changes-count'],
      })
      await queryClient.invalidateQueries({
        queryKey: ['pending-trust-changes'],
      })
      if (failed.length === 0) {
        triggerMutation.mutate({ recipeNames, runner })
        return
      }
      setTrustVerifyIssue({ runner, verify: res })
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Trust verification failed')
    } finally {
      toast.dismiss(toastId)
      setTrustVerifying(false)
    }
  }

  const runActionPending = triggerMutation.isPending || trustVerifying

  const columns: ColumnDef<AutoPkgRunRead>[] = [
    {
      id: 'expand',
      cell: ({ row }) => (
        <Button
          variant="ghost"
          size="sm"
          aria-label={
            resultsRunId === row.original.id
              ? 'Close run results'
              : 'View run results'
          }
          onClick={() =>
            setResultsRunId(
              resultsRunId === row.original.id ? null : row.original.id,
            )
          }
        >
          {resultsRunId === row.original.id ? (
            <ChevronDown className="h-4 w-4" />
          ) : (
            <ChevronRight className="h-4 w-4" />
          )}
        </Button>
      ),
    },
    {
      accessorKey: 'status',
      header: 'Status',
      cell: ({ row }) => (
        <Badge variant={statusVariant(row.original.status)}>
          {row.original.status}
        </Badge>
      ),
    },
    {
      accessorKey: 'runner_type',
      header: 'Runner',
      cell: ({ row }) => (
        <Badge variant="secondary">
          {row.original.runner_type === 'local' ? 'Local Mac' : 'GitHub'}
        </Badge>
      ),
    },
    {
      accessorKey: 'trigger_type',
      header: 'Trigger',
      cell: ({ row }) => (
        <Badge variant="outline">{row.original.trigger_type}</Badge>
      ),
    },
    {
      id: 'schedule',
      header: 'Schedule',
      cell: ({ row }) =>
        row.original.schedule_name ? (
          <span className="max-w-[140px] truncate text-sm">
            {row.original.schedule_name}
          </span>
        ) : (
          <span className="text-muted-foreground">—</span>
        ),
    },
    {
      accessorKey: 'triggered_by',
      header: 'Triggered By',
    },
    {
      id: 'stats',
      header: 'Results',
      cell: ({ row }) => {
        const r = row.original
        if (!r.total_recipes) return '—'
        return (
          <div className="flex gap-2">
            {r.recipes_imported ? (
              <Badge variant="default">{r.recipes_imported} imported</Badge>
            ) : null}
            {r.recipes_failed ? (
              <Badge variant="destructive">{r.recipes_failed} failed</Badge>
            ) : null}
            <span className="text-sm text-muted-foreground">
              {r.total_recipes} total
            </span>
          </div>
        )
      },
    },
    {
      accessorKey: 'created_at',
      header: 'Date',
      cell: ({ row }) => (
        <span suppressHydrationWarning className="text-sm">
          {formatDateTime(row.original.created_at)}
        </span>
      ),
    },
  ]

  return (
    <div className="flex h-[calc(100vh-3rem)] flex-col gap-4">
      <div className="flex items-center justify-between">
        <PageHeading icon={Play} accent="autopkg" title="AutoPkg Runs" />
        <TriggerRunDialog
          canTrigger={canTriggerRuns}
          onTrigger={onTriggerRunWithTrust}
          isPending={runActionPending}
          trustVerifying={trustVerifying}
        />

        {trustVerifyIssue ? (
          <TrustVerifyFailureDialog
            open
            onOpenChange={(o) => {
              if (!o) setTrustVerifyIssue(null)
            }}
            verify={trustVerifyIssue.verify}
            isContinuing={trustContinuePending}
            onStop={() => setTrustVerifyIssue(null)}
            onContinue={() => {
              const names = trustVerifyIssue.verify.results
                .filter((r) => r.status === 'verified')
                .map((r) => r.name)
              if (names.length === 0) {
                toast.error('No recipes left to run after trust check')
                setTrustVerifyIssue(null)
                return
              }
              setTrustContinuePending(true)
              triggerMutation.mutate(
                { recipeNames: names, runner: trustVerifyIssue.runner },
                {
                  onSettled: () => {
                    setTrustContinuePending(false)
                    setTrustVerifyIssue(null)
                  },
                },
              )
            }}
          />
        ) : null}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Select
          value={status || '_all'}
          onValueChange={(v) => {
            setStatus(v === '_all' ? null : v)
            setPage(1)
          }}
        >
          <SelectTrigger className="w-[150px]">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="_all">All Statuses</SelectItem>
            {STATUS_OPTIONS.map((s) => (
              <SelectItem key={s} value={s}>
                {s}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {status && (
          <Button
            variant="ghost"
            size="sm"
            aria-label="Clear filters"
            onClick={() => {
              setStatus(null)
              setPage(1)
            }}
          >
            <X className="h-4 w-4" />
            Clear
          </Button>
        )}
      </div>

      <div className="flex-1 min-h-0">
        <DataTable
          columns={columns}
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
        />
      </div>

      <Dialog
        open={!!resultsRunId}
        onOpenChange={(open) => {
          if (!open) setResultsRunId(null)
        }}
      >
        <DialogContent
          showCloseButton
          className="flex max-h-[85vh] flex-col gap-0 overflow-hidden p-0 sm:max-w-2xl"
        >
          <DialogHeader className="shrink-0 border-b px-6 pt-6 pr-14 pb-4">
            <DialogTitle>Run results</DialogTitle>
            <DialogDescription asChild>
              <div className="flex flex-col gap-2">
                <div className="flex flex-wrap gap-x-3 gap-y-1">
                  {resultsRun && !resultsRunLoading ? (
                    <>
                      <span suppressHydrationWarning>
                        {formatDateTime(resultsRun.created_at)}
                      </span>
                      <span className="text-muted-foreground">·</span>
                      <span className="capitalize">{resultsRun.status}</span>
                      {resultsRun.total_recipes != null && (
                        <>
                          <span className="text-muted-foreground">·</span>
                          <span>{resultsRun.total_recipes} recipes</span>
                        </>
                      )}
                    </>
                  ) : (
                    <span className="text-muted-foreground">Loading run…</span>
                  )}
                </div>
                {resultsRun?.github_run_url ? (
                  <a
                    href={resultsRun.github_run_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-sm font-medium text-primary underline-offset-4 hover:underline"
                  >
                    View on GitHub
                    <ExternalLink className="h-3.5 w-3.5" aria-hidden />
                  </a>
                ) : null}
              </div>
            </DialogDescription>
          </DialogHeader>
          {resultsRunLoading || !resultsRun ? (
            <div className="flex min-h-[min(200px,40vh)] items-center justify-center px-6 py-10">
              <Loader2
                className="h-8 w-8 animate-spin text-muted-foreground"
                aria-hidden
              />
            </div>
          ) : (
            <RunResultsScrollBody run={resultsRun} />
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}

function RecipeCheckItem({
  recipe,
  checked,
  onToggle,
  canRun,
}: {
  recipe: AutoPkgRecipeRead
  checked: boolean
  onToggle: () => void
  canRun: boolean
}) {
  return (
    <div
      role="option"
      aria-selected={checked}
      tabIndex={canRun ? 0 : -1}
      title={
        canRun
          ? undefined
          : 'Trust is failed or pending approval — resolve trust before running'
      }
      className={`flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left ${
        canRun
          ? 'cursor-pointer hover:bg-accent'
          : 'cursor-not-allowed opacity-60'
      }`}
      onClick={() => {
        if (canRun) onToggle()
      }}
      onKeyDown={(e) => {
        if (!canRun) return
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onToggle()
        }
      }}
    >
      <Checkbox
        checked={checked}
        disabled={!canRun}
        tabIndex={-1}
        className="pointer-events-none"
      />
      <span className="flex-1 truncate text-sm">{recipe.name}</span>
      {!canRun && (
        <Badge variant="secondary" className="shrink-0 text-xs">
          trust blocked
        </Badge>
      )}
      {recipe.last_run_status && (
        <Badge
          variant={
            lastRecipeRunLooksOk(recipe.last_run_status)
              ? 'default'
              : 'destructive'
          }
          className="shrink-0 text-xs"
        >
          {recipe.last_run_status}
        </Badge>
      )}
    </div>
  )
}

function TriggerRunDialog({
  canTrigger,
  onTrigger,
  isPending,
  trustVerifying = false,
}: {
  canTrigger: boolean
  onTrigger: (
    recipeNames: string[] | null,
    runner: 'github' | 'local',
  ) => void | Promise<void>
  isPending: boolean
  trustVerifying?: boolean
}) {
  const [open, setOpen] = useState(false)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [recipeSearch, setRecipeSearch] = useState('')
  const [runnerChoice, setRunnerChoice] = useState<
    'github' | 'local-manual' | 'local-daemon'
  >('github')

  const { data: uiSettings } = useQuery({
    queryKey: ['settings', 'ui'],
    queryFn: () => api.get<UiSettingsRead>('/settings/ui'),
    enabled: open,
  })

  const { data: recipes } = useQuery({
    queryKey: ['autopkg-recipes-enabled'],
    queryFn: () => fetchEnabledAutopkgRecipes(),
    enabled: open,
  })

  useEffect(() => {
    if (!open) return
    const saved =
      typeof window !== 'undefined'
        ? localStorage.getItem(RUNNER_STORAGE_KEY)
        : null
    const delivery =
      typeof window !== 'undefined'
        ? localStorage.getItem(RUNNER_LOCAL_DELIVERY_KEY)
        : null
    if (saved === 'github') {
      setRunnerChoice('github')
      return
    }
    if (saved === 'local') {
      setRunnerChoice(delivery === 'daemon' ? 'local-daemon' : 'local-manual')
      return
    }
    if (
      uiSettings?.autopkg_runner_mode === 'github' ||
      uiSettings?.autopkg_runner_mode === 'local'
    ) {
      setRunnerChoice(
        uiSettings.autopkg_runner_mode === 'local'
          ? delivery === 'daemon'
            ? 'local-daemon'
            : 'local-manual'
          : 'github',
      )
    }
  }, [open, uiSettings])

  const filtered = (recipes ?? []).filter((r) =>
    recipeSearch
      ? r.name.toLowerCase().includes(recipeSearch.toLowerCase()) ||
        r.identifier.toLowerCase().includes(recipeSearch.toLowerCase())
      : true,
  )

  const runnableInFilter = filtered.filter(canTriggerRunRecipe)

  const toggleRecipe = (name: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return next
    })
  }

  const toggleAll = () => {
    const allRunnableSelected =
      runnableInFilter.length > 0 &&
      runnableInFilter.every((r) => selected.has(r.name))
    if (allRunnableSelected) {
      setSelected(new Set())
    } else {
      setSelected(new Set(runnableInFilter.map((r) => r.name)))
    }
  }

  const handleTrigger = async () => {
    let names: string[] | null = null
    if (selected.size > 0) {
      const runnableNames = [...selected].filter((n) => {
        const r = recipes?.find((x) => x.name === n)
        return r && canTriggerRunRecipe(r)
      })
      if (runnableNames.length === 0) {
        toast.error('Selected recipes cannot run until trust is resolved')
        return
      }
      names = runnableNames
    }
    const apiRunner = runnerChoice === 'github' ? 'github' : 'local'
    localStorage.setItem(RUNNER_STORAGE_KEY, apiRunner)
    if (apiRunner === 'local') {
      localStorage.setItem(
        RUNNER_LOCAL_DELIVERY_KEY,
        runnerChoice === 'local-daemon' ? 'daemon' : 'manual',
      )
    }
    await Promise.resolve(onTrigger(names, apiRunner))
    setOpen(false)
    setSelected(new Set())
    setRecipeSearch('')
  }

  if (!canTrigger) {
    return null
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>
          <Play className="h-4 w-4" />
          Trigger Run
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[80vh] sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Trigger AutoPkg Run</DialogTitle>
          <DialogDescription>
            Select specific recipes or run all enabled overrides. Trust is
            re-checked against GitHub before the run starts; recipes that fail
            live verification can be skipped.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div className="grid gap-2">
            <Label htmlFor="autopkg-runner">Runner</Label>
            <Select
              value={runnerChoice}
              onValueChange={(v) =>
                setRunnerChoice(v as 'github' | 'local-manual' | 'local-daemon')
              }
            >
              <SelectTrigger id="autopkg-runner" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="github">GitHub Actions</SelectItem>
                <SelectItem value="local-manual">
                  Local Mac (copy shell command)
                </SelectItem>
                <SelectItem value="local-daemon">
                  Local Mac (automated daemon)
                </SelectItem>
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              Local creates a pending run — either run{' '}
              <code className="text-xs">poll_local_autopkg.sh</code> with a{' '}
              <code className="text-xs">LOCAL_RUNNER_TOKEN</code> or use the
              manual shell command. See{' '}
              <code className="text-xs">docs/local-autopkg-runner.md</code>.
            </p>
          </div>

          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="Filter recipes..."
              value={recipeSearch}
              onChange={(e) => setRecipeSearch(e.target.value)}
              className="pl-9"
            />
          </div>

          <div className="flex items-center justify-between px-1">
            <div
              role="option"
              aria-selected={
                runnableInFilter.length > 0 &&
                runnableInFilter.every((r) => selected.has(r.name))
              }
              tabIndex={runnableInFilter.length > 0 ? 0 : -1}
              className={`flex items-center gap-2 text-sm ${
                runnableInFilter.length > 0
                  ? 'cursor-pointer'
                  : 'cursor-not-allowed opacity-60'
              }`}
              onClick={() => {
                if (runnableInFilter.length > 0) toggleAll()
              }}
              onKeyDown={(e) => {
                if (runnableInFilter.length === 0) return
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  toggleAll()
                }
              }}
            >
              <Checkbox
                checked={
                  runnableInFilter.length > 0 &&
                  runnableInFilter.every((r) => selected.has(r.name))
                }
                disabled={runnableInFilter.length === 0}
                tabIndex={-1}
                className="pointer-events-none"
                aria-label="Select all runnable recipes"
              />
              Select all runnable ({runnableInFilter.length})
            </div>
            {selected.size > 0 && (
              <span className="text-sm text-muted-foreground">
                {selected.size} selected
              </span>
            )}
          </div>

          <div className="max-h-[40vh] space-y-1 overflow-y-auto rounded-md border p-2">
            {filtered.length === 0 ? (
              <p className="py-4 text-center text-sm text-muted-foreground">
                No enabled recipes found.
              </p>
            ) : (
              <>
                {runnableInFilter.length === 0 && (
                  <p className="mb-2 rounded-md border border-dashed bg-muted/40 px-2 py-2 text-center text-xs text-muted-foreground">
                    Nothing here is runnable — trust is failed or pending for
                    every match.
                  </p>
                )}
                {filtered.map((recipe) => (
                  <RecipeCheckItem
                    key={recipe.id}
                    recipe={recipe}
                    checked={selected.has(recipe.name)}
                    onToggle={() => toggleRecipe(recipe.name)}
                    canRun={canTriggerRunRecipe(recipe)}
                  />
                ))}
              </>
            )}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button
            onClick={() => void handleTrigger()}
            disabled={isPending || trustVerifying}
          >
            {trustVerifying || isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Play className="h-4 w-4" />
            )}
            {trustVerifying
              ? 'Verifying trust…'
              : isPending
                ? 'Triggering...'
                : selected.size > 0
                  ? `Run ${selected.size} Recipe${selected.size > 1 ? 's' : ''}`
                  : 'Run All Enabled'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function statusVariantResult(s: string) {
  switch (s) {
    case 'success':
    case 'imported':
      return 'default' as const
    case 'failed':
    case 'trust_failed':
      return 'destructive' as const
    default:
      return 'secondary' as const
  }
}

/** Scrollable results list inside the run dialog (header is fixed above). */
function RunResultsScrollBody({ run }: { run: AutoPkgRunRead }) {
  if (!run?.results?.length) {
    return (
      <div className="max-h-[min(65vh,calc(85vh-9rem))] overflow-y-auto px-6 py-4">
        <p className="text-muted-foreground text-sm">No results for this run</p>
      </div>
    )
  }

  return (
    <div className="max-h-[min(65vh,calc(85vh-9rem))] min-h-0 overflow-y-auto px-6 py-4">
      <div className="space-y-2">
        {run.results.map((result) => (
          <div
            key={result.id}
            className="flex flex-col gap-2 rounded-md border p-3 sm:flex-row sm:items-center sm:justify-between"
          >
            <div className="flex min-w-0 flex-wrap items-center gap-2 sm:gap-3">
              <Badge
                variant={statusVariantResult(result.status)}
                className="shrink-0"
              >
                {result.status}
              </Badge>
              <span className="font-medium break-words">
                {result.imported_display_name?.trim() || result.recipe_name}
              </span>
              {result.imported_version && (
                <span className="text-sm text-muted-foreground">
                  v{result.imported_version}
                </span>
              )}
            </div>
            <div className="flex shrink-0 flex-wrap items-center gap-2">
              <Badge
                variant={
                  result.approval_status === 'approved' ||
                  result.approval_status === 'auto_approved'
                    ? 'default'
                    : result.approval_status === 'pending'
                      ? 'secondary'
                      : 'destructive'
                }
              >
                {result.approval_status}
              </Badge>
              {result.duration_seconds != null && (
                <span className="text-sm text-muted-foreground">
                  {result.duration_seconds}s
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
