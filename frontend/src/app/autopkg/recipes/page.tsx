import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { RowSelectionState, VisibilityState } from '@tanstack/react-table'
import { useAtom } from 'jotai'
import {
  BookOpen,
  Compass,
  FileUp,
  Loader2,
  Play,
  Search,
  ShieldAlert,
  ShieldCheck,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import { useAuth } from '@/components/auth-provider'
import {
  recipeListColumns,
  recipeListDefaultColumnVisibility,
} from '@/components/autopkg/recipe-list-columns'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { ColumnVisibilityMenu, DataTable } from '@/components/data-table'
import { PageFilters } from '@/components/page-filters'
import { PageHeading } from '@/components/page-heading'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
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
import { Textarea } from '@/components/ui/textarea'
import { useAutopkgQuickRun } from '@/hooks/use-autopkg-quick-run'
import { useDocumentTitle } from '@/hooks/use-document-title'
import type { PkginfoItemMeta } from '@/hooks/use-pkginfo-display-labels'
import {
  type AutoPkgRecipeRead,
  api,
  type PaginatedResponse,
  type TrustPendingCountResponse,
} from '@/lib/api'
import { autopkgRecipesPageListAtom } from '@/lib/atoms/autopkg-recipes-page-list'
import { recipePkginfoKey } from '@/lib/autopkg-recipe'
import { QuickRunDialog, TrustVerifyFailureDialog } from '@/lib/autopkg-run'
import { PAGE_KEYS } from '@/lib/page-keys'

/** XML/YAML text, or binary plist as base64 (matches backend ``import-override``). */
async function fileToImportOverrideContent(file: File): Promise<string> {
  const buf = await file.arrayBuffer()
  const u8 = new Uint8Array(buf)
  const head = new TextDecoder('latin1').decode(u8.subarray(0, 8))
  if (head === 'bplist00') {
    let binary = ''
    const chunk = 8192
    for (let i = 0; i < u8.length; i += chunk) {
      binary += String.fromCharCode(
        ...u8.subarray(i, Math.min(i + chunk, u8.length)),
      )
    }
    return btoa(binary)
  }
  return new TextDecoder('utf-8').decode(u8)
}

export default function RecipesPage() {
  useDocumentTitle('AutoPkg', 'Recipes')
  const { canWrite, canRead, loading: authLoading } = useAuth()
  const canEditRecipes = canWrite(PAGE_KEYS.autopkgRecipes)
  const canRun = canWrite(PAGE_KEYS.autopkgRuns)
  const canVerifyTrustBtn = canWrite(PAGE_KEYS.autopkgApprovals)
  const canVerifyAllRepos = canWrite(PAGE_KEYS.autopkgDiscover)
  const canSeeApprovals = !authLoading && canRead(PAGE_KEYS.autopkgApprovals)

  const { data: pendingTrustHeader } = useQuery({
    queryKey: ['pending-trust-changes-count'],
    queryFn: () =>
      api.get<TrustPendingCountResponse>(
        '/autopkg/trust-changes/pending-count',
      ),
    enabled: canSeeApprovals,
    staleTime: 30_000,
  })
  const pendingTrustQueueCount = pendingTrustHeader?.count ?? 0

  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [listState, setListState] = useAtom(autopkgRecipesPageListAtom)
  const { search, enabled, trustStatus, page, pageSize } = listState
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({})
  const [columnVisibility, setColumnVisibility] = useState<VisibilityState>(
    recipeListDefaultColumnVisibility,
  )

  const {
    quickRun,
    setQuickRun,
    runActionPending,
    trustVerifying,
    trustVerifyIssue,
    onQuickRunConfirm,
    onTrustDialogStop,
    onTrustDialogContinue,
    trustContinuePending,
    triggerRunMutation,
  } = useAutopkgQuickRun({ onRunSuccess: () => setRowSelection({}) })

  useEffect(() => {
    if (!canRun) setRowSelection({})
  }, [canRun])

  const [searchParams] = useSearchParams()
  useEffect(() => {
    const trustFromUrl = searchParams.get('trust_status')?.trim()
    if (
      !trustFromUrl ||
      !['verified', 'failed', 'pending_approval', 'unknown'].includes(
        trustFromUrl,
      )
    ) {
      return
    }
    setListState((prev) =>
      prev.trustStatus === trustFromUrl
        ? prev
        : { ...prev, trustStatus: trustFromUrl, page: 1 },
    )
  }, [searchParams, setListState])

  const [importOpen, setImportOpen] = useState(false)
  const [importContent, setImportContent] = useState('')
  const [importBatchItems, setImportBatchItems] = useState<
    { fileName: string; content: string }[] | null
  >(null)
  const [importName, setImportName] = useState('')
  const [importSourceRepo, setImportSourceRepo] = useState('')
  const [importRefreshTrust, setImportRefreshTrust] = useState(true)

  const { data: recipesPage, isLoading } = useQuery({
    queryKey: ['autopkg-recipes', page, pageSize, search, enabled, trustStatus],
    queryFn: () => {
      const params = new URLSearchParams()
      params.set('page', String(page))
      params.set('page_size', String(pageSize))
      const q = search.trim()
      if (q) params.set('search', q)
      if (enabled === 'true' || enabled === 'false')
        params.set('enabled', enabled)
      const ts = trustStatus.trim()
      if (
        ts === 'verified' ||
        ts === 'failed' ||
        ts === 'pending_approval' ||
        ts === 'unknown'
      ) {
        params.set('trust_status', ts)
      }
      return api.get<PaginatedResponse<AutoPkgRecipeRead>>(
        `/autopkg/recipes?${params.toString()}`,
      )
    },
  })

  const recipes = recipesPage?.items ?? []

  const pkgMeta = useMemo(() => {
    if (!recipes.length) return undefined
    const m: Record<string, PkginfoItemMeta> = {}
    for (const r of recipes) {
      const key = recipePkginfoKey(r)
      m[key] = {
        displayName: r.pkginfo_display_name?.trim() || key,
        iconName: r.pkginfo_icon_name?.trim() ?? null,
      }
    }
    return m
  }, [recipes])

  const updateMutation = useMutation({
    mutationFn: ({ id, ...data }: { id: string } & Record<string, unknown>) =>
      api.put(`/autopkg/recipes/${id}`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['autopkg-recipes'] })
    },
    onError: (err: Error) => toast.error(err.message),
  })

  const [verifyingTrustId, setVerifyingTrustId] = useState<string | null>(null)

  const verifyTrustMutation = useMutation({
    mutationFn: (id: string) => {
      setVerifyingTrustId(id)
      return api.post<{ name: string; trust_status: string; error?: string }>(
        `/autopkg/recipes/${id}/verify-trust`,
      )
    },
    onSuccess: (data) => {
      setVerifyingTrustId(null)
      if (data.trust_status === 'verified') {
        toast.success(`${data.name}: Trust verified`)
      } else if (data.trust_status === 'pending_approval') {
        toast.warning(`${data.name}: Trust changed — approval required`)
      } else {
        toast.info(`${data.name}: ${data.error || 'Could not verify trust'}`)
      }
      queryClient.invalidateQueries({ queryKey: ['autopkg-recipes'] })
      queryClient.invalidateQueries({
        queryKey: ['pending-trust-changes-count'],
      })
      queryClient.invalidateQueries({ queryKey: ['pending-trust-changes'] })
    },
    onError: (err: Error) => {
      setVerifyingTrustId(null)
      toast.error(err.message)
    },
  })

  const verifyAllMutation = useMutation({
    mutationFn: () =>
      api.post<{
        total: number
        verified: number
        failed: number
        errors: number
      }>('/autopkg/repos/update'),
    onSuccess: (data) => {
      toast.success(
        `Verified ${data.total} recipes: ${data.verified} OK, ${data.failed} changed, ${data.errors} errors`,
      )
      queryClient.invalidateQueries({ queryKey: ['autopkg-recipes'] })
      queryClient.invalidateQueries({
        queryKey: ['pending-trust-changes-count'],
      })
      queryClient.invalidateQueries({ queryKey: ['pending-trust-changes'] })
    },
    onError: (err: Error) => toast.error(err.message),
  })

  const [deletingRecipe, setDeletingRecipe] =
    useState<AutoPkgRecipeRead | null>(null)

  const importOverrideMutation = useMutation({
    mutationFn: (body: {
      content: string
      name?: string | null
      source_repo_full_name?: string | null
      refresh_trust: boolean
    }) =>
      api.post<AutoPkgRecipeRead>('/autopkg/recipes/import-override', {
        content: body.content,
        name: body.name?.trim() || null,
        source_repo_full_name: body.source_repo_full_name?.trim() || null,
        is_enabled: true,
        auto_promote: false,
        refresh_trust: body.refresh_trust,
      }),
    onSuccess: (recipe) => {
      toast.success(`Imported override ${recipe.name}`)
      setImportOpen(false)
      setImportContent('')
      setImportBatchItems(null)
      setImportName('')
      setImportSourceRepo('')
      setImportRefreshTrust(true)
      queryClient.invalidateQueries({ queryKey: ['autopkg-recipes'] })
    },
    onError: (err: Error) => toast.error(err.message),
  })

  const importBatchMutation = useMutation({
    mutationFn: async (args: {
      items: { fileName: string; content: string }[]
      refresh_trust: boolean
    }) => {
      const imported: string[] = []
      const failed: { file: string; error: string }[] = []
      for (const item of args.items) {
        try {
          const recipe = await api.post<AutoPkgRecipeRead>(
            '/autopkg/recipes/import-override',
            {
              content: item.content,
              name: null,
              source_repo_full_name: null,
              is_enabled: true,
              auto_promote: false,
              refresh_trust: args.refresh_trust,
            },
          )
          imported.push(recipe.name)
        } catch (e) {
          failed.push({
            file: item.fileName,
            error: e instanceof Error ? e.message : String(e),
          })
        }
      }
      return { imported, failed }
    },
    onSuccess: (data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['autopkg-recipes'] })
      if (data.failed.length === 0) {
        toast.success(
          `Imported ${data.imported.length} override${data.imported.length === 1 ? '' : 's'}`,
        )
        setImportOpen(false)
        setImportContent('')
        setImportBatchItems(null)
        setImportName('')
        setImportSourceRepo('')
        setImportRefreshTrust(true)
      } else if (data.imported.length === 0) {
        toast.error(
          `Failed to import ${data.failed.length} file${data.failed.length === 1 ? '' : 's'}`,
          {
            description: data.failed
              .map((f) => `${f.file}: ${f.error}`)
              .join('\n'),
          },
        )
      } else {
        toast.warning(
          `Imported ${data.imported.length}, ${data.failed.length} failed`,
          {
            description: data.failed
              .map((f) => `${f.file}: ${f.error}`)
              .join('\n'),
          },
        )
        const failedNames = new Set(data.failed.map((f) => f.file))
        setImportBatchItems(
          variables.items.filter((i) => failedNames.has(i.fileName)),
        )
      }
    },
    onError: (err: Error) => toast.error(err.message),
  })

  const inlineDeleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/autopkg/recipes/${id}`),
    onSuccess: () => {
      toast.success(`Deleted override ${deletingRecipe?.name ?? 'recipe'}`)
      setDeletingRecipe(null)
      queryClient.invalidateQueries({ queryKey: ['autopkg-recipes'] })
    },
    onError: (err: Error) => toast.error(err.message),
  })

  const pendingRunRecipeName =
    triggerRunMutation.isPending &&
    triggerRunMutation.variables?.recipeNames?.length === 1
      ? triggerRunMutation.variables.recipeNames[0]
      : trustVerifying && quickRun?.mode === 'single'
        ? quickRun.recipe.name
        : null

  const pendingRunAll =
    (triggerRunMutation.isPending &&
      (triggerRunMutation.variables?.recipeNames === null ||
        triggerRunMutation.variables?.recipeNames === undefined)) ||
    (trustVerifying && quickRun?.mode === 'all')

  const recipeById = useMemo(
    () => new Map(recipes.map((r) => [r.id, r])),
    [recipes],
  )

  const selectedRecipes = useMemo(() => {
    return Object.keys(rowSelection)
      .filter((id) => rowSelection[id])
      .map((id) => recipeById.get(id))
      .filter((r): r is AutoPkgRecipeRead => r != null)
  }, [rowSelection, recipeById])

  /** Header "Run selected" is loading (explicit list while selection is non-empty). */
  const pendingRunSelectedList =
    (triggerRunMutation.isPending &&
      selectedRecipes.length > 0 &&
      triggerRunMutation.variables?.recipeNames != null &&
      triggerRunMutation.variables.recipeNames.length >= 1) ||
    (trustVerifying && quickRun?.mode === 'selected')

  const onToggleEnabled = useCallback(
    (id: string, val: boolean) =>
      updateMutation.mutate({ id, is_enabled: val }),
    [updateMutation],
  )

  const onToggleAutoPromote = useCallback(
    (id: string, val: boolean) =>
      updateMutation.mutate({ id, auto_promote: val }),
    [updateMutation],
  )

  const columns = useMemo(
    () =>
      recipeListColumns(
        pkgMeta,
        onToggleEnabled,
        onToggleAutoPromote,
        (recipe) => navigate(`/autopkg/recipes/${recipe.id}`),
        (recipe) => setQuickRun({ mode: 'single', recipe }),
        (id) => verifyTrustMutation.mutate(id),
        setDeletingRecipe,
        verifyingTrustId,
        pendingRunRecipeName,
        runActionPending,
        {
          canEditRecipes,
          canRun,
          canVerifyTrust: canVerifyTrustBtn,
        },
      ),
    [
      pkgMeta,
      navigate,
      verifyingTrustId,
      pendingRunRecipeName,
      runActionPending,
      verifyTrustMutation,
      canEditRecipes,
      canRun,
      canVerifyTrustBtn,
      onToggleEnabled,
      onToggleAutoPromote,
      setQuickRun,
    ],
  )

  const hasSheetFilters = Boolean(enabled) || Boolean(trustStatus.trim())
  const activeFilterCount = [enabled, trustStatus.trim()].filter(Boolean).length
  const activeFilters = [
    ...(enabled
      ? [
          {
            id: 'enabled',
            label: enabled === 'true' ? 'Enabled' : 'Disabled',
            onRemove: () => {
              setRowSelection({})
              setListState((p) => ({ ...p, enabled: '', page: 1 }))
            },
          },
        ]
      : []),
    ...(trustStatus.trim()
      ? [
          {
            id: 'trustStatus',
            label: `Trust: ${trustStatus.replace('_', ' ')}`,
            onRemove: () => {
              setRowSelection({})
              setListState((p) => ({ ...p, trustStatus: '', page: 1 }))
            },
          },
        ]
      : []),
  ]

  return (
    <div className="flex h-[calc(100vh-3rem)] min-w-0 w-full max-w-full flex-col gap-4">
      <PageHeading
        icon={BookOpen}
        accent="autopkg"
        title="Recipe Management"
        afterTitle={
          canSeeApprovals && pendingTrustQueueCount > 0 ? (
            <Badge
              asChild
              variant="default"
              className="shrink-0 bg-gruvbox-yellow text-primary-foreground hover:bg-gruvbox-yellow/90"
            >
              <Link
                to="/approvals"
                className="inline-flex items-center gap-1.5"
                title="Open Approvals to review trust changes"
              >
                <ShieldAlert className="size-3.5" aria-hidden />
                {pendingTrustQueueCount > 99 ? '99+' : pendingTrustQueueCount}{' '}
                pending approval
                {pendingTrustQueueCount === 1 ? '' : 's'}
              </Link>
            </Badge>
          ) : null
        }
        actions={
          <>
            {canRun && selectedRecipes.length > 0 ? (
              <>
                <Button
                  size="sm"
                  disabled={runActionPending}
                  onClick={() =>
                    setQuickRun({ mode: 'selected', recipes: selectedRecipes })
                  }
                >
                  {pendingRunSelectedList ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Play className="h-4 w-4" />
                  )}
                  Run selected ({selectedRecipes.length})
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={runActionPending}
                  onClick={() => setRowSelection({})}
                >
                  Clear selection
                </Button>
              </>
            ) : canRun ? (
              <Button
                size="sm"
                disabled={runActionPending}
                onClick={() => setQuickRun({ mode: 'all' })}
              >
                {pendingRunAll ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Play className="h-4 w-4" />
                )}
                Run all
              </Button>
            ) : null}
            {canVerifyAllRepos ? (
              <Button
                variant="outline"
                size="sm"
                disabled={verifyAllMutation.isPending}
                onClick={() => verifyAllMutation.mutate()}
              >
                {verifyAllMutation.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <ShieldCheck className="h-4 w-4" />
                )}
                Verify All
              </Button>
            ) : null}
            <Button variant="outline" asChild>
              <Link to="/autopkg/discover">
                <Compass className="h-4 w-4" />
                Discover
              </Link>
            </Button>
            {canEditRecipes ? (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setImportOpen(true)}
              >
                <FileUp className="h-4 w-4" />
                Import
              </Button>
            ) : null}
          </>
        }
      />

      <PageFilters
        isFiltered={hasSheetFilters}
        activeFilterCount={activeFilterCount}
        activeFilters={activeFilters}
        sheetDescription="Refine the recipe list."
        onClear={() => {
          setRowSelection({})
          setListState((p) => ({
            ...p,
            enabled: '',
            trustStatus: '',
            page: 1,
          }))
        }}
        trailing={
          <ColumnVisibilityMenu
            columns={columns}
            columnVisibility={columnVisibility}
            defaultColumnVisibility={recipeListDefaultColumnVisibility}
            onColumnVisibilityChange={setColumnVisibility}
          />
        }
        search={
          <div className="relative max-w-sm">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="Search recipes..."
              value={search}
              onChange={(e) => {
                setRowSelection({})
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
          value={enabled || '_all'}
          onValueChange={(v) => {
            setRowSelection({})
            setListState((p) => ({
              ...p,
              enabled: v === '_all' ? '' : v,
              page: 1,
            }))
          }}
        >
          <SelectTrigger className="w-full">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="_all">All Statuses</SelectItem>
            <SelectItem value="true">Enabled</SelectItem>
            <SelectItem value="false">Disabled</SelectItem>
          </SelectContent>
        </Select>

        <Select
          value={trustStatus.trim() || '_all'}
          onValueChange={(v) => {
            setRowSelection({})
            setListState((p) => ({
              ...p,
              trustStatus: v === '_all' ? '' : v,
              page: 1,
            }))
          }}
        >
          <SelectTrigger className="w-full" aria-label="Filter by trust">
            <SelectValue placeholder="Trust" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="_all">All Trust</SelectItem>
            <SelectItem value="verified">Verified</SelectItem>
            <SelectItem value="failed">Failed</SelectItem>
            <SelectItem value="pending_approval">Pending</SelectItem>
            <SelectItem value="unknown">Unknown</SelectItem>
          </SelectContent>
        </Select>
      </PageFilters>

      <div className="min-h-0 min-w-0 flex-1">
        <DataTable
          columns={columns}
          data={recipes}
          pageCount={Math.max(1, recipesPage?.total_pages ?? 1)}
          page={page}
          pageSize={pageSize}
          total={recipesPage?.total}
          onPageChange={(p) => {
            setRowSelection({})
            setListState((s) => ({ ...s, page: p }))
          }}
          onPageSizeChange={(size) => {
            setRowSelection({})
            setListState((s) => ({ ...s, pageSize: size, page: 1 }))
          }}
          isLoading={isLoading}
          defaultColumnVisibility={recipeListDefaultColumnVisibility}
          columnVisibility={columnVisibility}
          onColumnVisibilityChange={setColumnVisibility}
          hideColumnPicker
          enableRowSelection={canRun}
          rowSelection={rowSelection}
          onRowSelectionChange={setRowSelection}
          getRowId={(row) => row.id}
        />
      </div>

      <QuickRunDialog
        open={quickRun !== null}
        onOpenChange={(open) => {
          if (!open) setQuickRun(null)
        }}
        target={quickRun}
        isPending={triggerRunMutation.isPending}
        trustVerifying={trustVerifying}
        onConfirm={onQuickRunConfirm}
      />

      {trustVerifyIssue ? (
        <TrustVerifyFailureDialog
          open
          onOpenChange={(o) => {
            if (!o) onTrustDialogStop()
          }}
          verify={trustVerifyIssue.verify}
          isContinuing={trustContinuePending}
          onStop={onTrustDialogStop}
          onContinue={onTrustDialogContinue}
        />
      ) : null}

      <Dialog
        open={importOpen}
        onOpenChange={(open) => {
          setImportOpen(open)
          if (!open) {
            setImportContent('')
            setImportBatchItems(null)
            setImportName('')
            setImportSourceRepo('')
            setImportRefreshTrust(true)
          }
        }}
      >
        <DialogContent className="flex max-h-[90dvh] flex-col gap-0 overflow-hidden p-0 sm:max-h-[85vh] sm:max-w-[1200px]">
          <DialogHeader className="shrink-0 border-b px-6 pt-6 pr-14 pb-4">
            <DialogTitle>Import existing override</DialogTitle>
            <DialogDescription>
              Paste XML plist text, YAML, JSON, or base64-encoded binary plist
              from your AutoPkg recipe repo or{' '}
              <span className="font-mono">
                ~/Library/AutoPkg/RecipeOverrides
              </span>
              . Identifier must not already exist in Automunki. Choose multiple
              files to import all at once (optional name/repo and editing are
              skipped for batch imports).
            </DialogDescription>
          </DialogHeader>
          <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-6 py-4">
            <div className="space-y-2">
              <Label htmlFor="import-override-file">File (optional)</Label>
              <Input
                id="import-override-file"
                type="file"
                multiple
                accept=".plist,.recipe,.yaml,.yml,text/plain,application/octet-stream"
                className="cursor-pointer"
                onChange={async (e) => {
                  const input = e.target
                  // Copy before clearing: ``FileList`` is live; resetting value empties it.
                  const files = Array.from(input.files ?? [])
                  input.value = ''
                  if (files.length === 0) return
                  try {
                    if (files.length === 1) {
                      setImportBatchItems(null)
                      const text = await fileToImportOverrideContent(files[0])
                      setImportContent(text)
                      toast.success(`Loaded ${files[0].name}`)
                    } else {
                      setImportContent('')
                      setImportName('')
                      setImportSourceRepo('')
                      const items = await Promise.all(
                        files.map(async (f) => ({
                          fileName: f.name,
                          content: await fileToImportOverrideContent(f),
                        })),
                      )
                      setImportBatchItems(items)
                      toast.success(
                        `Loaded ${items.length} files — review and Import all`,
                      )
                    }
                  } catch {
                    toast.error('Could not read file(s)')
                  }
                }}
              />
            </div>
            {importBatchItems && importBatchItems.length > 0 ? (
              <div className="space-y-2">
                <Label>Files to import ({importBatchItems.length})</Label>
                <ul className="max-h-48 overflow-y-auto rounded-md border px-3 py-2 text-sm font-mono">
                  {importBatchItems.map((item) => (
                    <li key={item.fileName} className="truncate py-0.5">
                      {item.fileName}
                    </li>
                  ))}
                </ul>
                <p className="text-xs text-muted-foreground">
                  Each file is imported with default name from its identifier.
                  Use a single file if you need optional fields or to edit
                  content before importing.
                </p>
              </div>
            ) : (
              <>
                <div className="space-y-2">
                  <Label htmlFor="import-override-content">
                    Override content
                  </Label>
                  <Textarea
                    id="import-override-content"
                    value={importContent}
                    onChange={(e) => {
                      setImportContent(e.target.value)
                      if (e.target.value.trim()) setImportBatchItems(null)
                    }}
                    placeholder="<?xml version=&quot;1.0&quot;… or base64 bplist…"
                    rows={12}
                    className="font-mono text-xs min-h-[200px]"
                  />
                </div>
                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="import-name">Display name (optional)</Label>
                    <Input
                      id="import-name"
                      value={importName}
                      onChange={(e) => setImportName(e.target.value)}
                      placeholder="Defaults to last segment of Identifier"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="import-repo">Source repo (optional)</Label>
                    <Input
                      id="import-repo"
                      value={importSourceRepo}
                      onChange={(e) => setImportSourceRepo(e.target.value)}
                      placeholder="owner/repo"
                      className="font-mono text-sm"
                    />
                  </div>
                </div>
              </>
            )}
            <div className="flex items-center gap-3 rounded-md border px-3 py-2">
              <Switch
                id="import-refresh-trust"
                checked={importRefreshTrust}
                onCheckedChange={setImportRefreshTrust}
              />
              <Label htmlFor="import-refresh-trust" className="cursor-pointer">
                Resolve trust from GitHub
              </Label>
            </div>
            <p className="text-xs text-muted-foreground">
              When enabled, parent recipes are hashed via the GitHub API and
              trust is marked verified. Turn off to import only the plist (trust
              stays unknown; use &quot;Re-fetch Trust&quot; in the recipe editor
              later).
            </p>
          </div>
          <DialogFooter className="shrink-0 gap-2 border-t bg-background px-6 py-4 sm:rounded-b-lg">
            <Button
              variant="outline"
              onClick={() => setImportOpen(false)}
              className="w-full sm:w-auto"
            >
              Cancel
            </Button>
            <Button
              disabled={
                importBatchItems && importBatchItems.length > 0
                  ? importBatchMutation.isPending
                  : !importContent.trim() || importOverrideMutation.isPending
              }
              className="w-full sm:w-auto"
              onClick={() => {
                if (importBatchItems && importBatchItems.length > 0) {
                  importBatchMutation.mutate({
                    items: importBatchItems,
                    refresh_trust: importRefreshTrust,
                  })
                } else {
                  importOverrideMutation.mutate({
                    content: importContent,
                    name: importName || null,
                    source_repo_full_name: importSourceRepo || null,
                    refresh_trust: importRefreshTrust,
                  })
                }
              }}
            >
              {importBatchMutation.isPending ||
              importOverrideMutation.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <FileUp className="mr-2 h-4 w-4" />
              )}
              {importBatchItems && importBatchItems.length > 0
                ? `Import all (${importBatchItems.length})`
                : 'Import'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={!!deletingRecipe}
        onOpenChange={(open) => {
          if (!open) setDeletingRecipe(null)
        }}
        title="Delete Override"
        description={
          <>
            Are you sure you want to delete the override for{' '}
            <strong>{deletingRecipe?.name}</strong>? This cannot be undone.
          </>
        }
        isPending={inlineDeleteMutation.isPending}
        onConfirm={() => {
          if (deletingRecipe) {
            inlineDeleteMutation.mutate(deletingRecipe.id)
          }
        }}
        contentClassName="max-w-sm"
      />
    </div>
  )
}
