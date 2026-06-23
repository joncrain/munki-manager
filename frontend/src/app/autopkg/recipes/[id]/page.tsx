import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, Loader2, Pencil, Play, Save, Trash2, X } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useAuth } from '@/components/auth-provider'
import {
  RecipeOverrideEditor,
  type RecipeOverrideToolbarApi,
} from '@/components/autopkg-recipe-override-editor'
import { RecipeTrustStatusBadge } from '@/components/recipe-trust-badge'
import { SoftwareIcon } from '@/components/software-icon'
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb'
import { Button } from '@/components/ui/button'
import { useAutopkgQuickRun } from '@/hooks/use-autopkg-quick-run'
import { useDocumentTitle } from '@/hooks/use-document-title'
import {
  type PkginfoItemMeta,
  usePkginfoItemMeta,
} from '@/hooks/use-pkginfo-display-labels'
import { type AutoPkgRecipeRead, api } from '@/lib/api'
import { recipeListIconName, recipePkginfoKey } from '@/lib/autopkg-recipe'
import {
  canTriggerRunRecipe,
  QuickRunDialog,
  TrustVerifyFailureDialog,
} from '@/lib/autopkg-run'
import { munkiAccents } from '@/lib/munki-accents'
import { PAGE_KEYS } from '@/lib/page-keys'
import { cn } from '@/lib/utils'

export default function RecipeOverrideEditPage() {
  const { canWrite } = useAuth()
  const canEditRecipes = canWrite(PAGE_KEYS.autopkgRecipes)
  const canRun = canWrite(PAGE_KEYS.autopkgRuns)

  const params = useParams()
  const navigate = useNavigate()
  const id = params.id as string
  const [editing, setEditing] = useState(false)
  const [editorKey, setEditorKey] = useState(0)
  const [toolbar, setToolbar] = useState<RecipeOverrideToolbarApi | null>(null)
  const [openDelete, setOpenDelete] = useState<(() => void) | null>(null)

  const effectiveEditing = editing && canEditRecipes
  const hasUnsavedChanges = Boolean(effectiveEditing && toolbar?.isDirty)

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
  } = useAutopkgQuickRun()

  useEffect(() => {
    setToolbar(null)
    setEditing(false)
    setEditorKey((k) => k + 1)
  }, [id])

  useEffect(() => {
    if (!canEditRecipes) {
      setEditing(false)
      setToolbar(null)
    }
  }, [canEditRecipes])

  const handleCancelEdit = useCallback(() => {
    setEditing(false)
    setEditorKey((k) => k + 1)
  }, [])

  const registerDelete = useCallback((fn: (() => void) | null) => {
    // Store a function in state — pass an updater so React does not invoke it.
    setOpenDelete(() => fn)
  }, [])

  const confirmLoseChanges = useCallback(() => {
    if (!hasUnsavedChanges) return true
    return window.confirm('You have unsaved changes. Discard them?')
  }, [hasUnsavedChanges])

  useEffect(() => {
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      if (!hasUnsavedChanges) return
      e.preventDefault()
    }
    window.addEventListener('beforeunload', onBeforeUnload)
    return () => window.removeEventListener('beforeunload', onBeforeUnload)
  }, [hasUnsavedChanges])

  const {
    data: recipe,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ['autopkg-recipe', id],
    queryFn: () => api.get<AutoPkgRecipeRead>(`/autopkg/recipes/${id}`),
  })

  useDocumentTitle('AutoPkg', 'Recipes', recipe?.name)

  const pkgKey = recipe ? recipePkginfoKey(recipe) : ''
  const { data: pkgMeta } = usePkginfoItemMeta(recipe ? [pkgKey] : [])
  const meta: PkginfoItemMeta | undefined = pkgMeta?.[pkgKey]

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12 text-muted-foreground">
        Loading...
      </div>
    )
  }

  if (isError || !recipe) {
    return (
      <div className="space-y-4">
        <p className="text-muted-foreground">Recipe not found.</p>
        <Button variant="outline" asChild>
          <Link to="/autopkg/recipes">Back to recipes</Link>
        </Button>
      </div>
    )
  }

  const runThisPending =
    (triggerRunMutation.isPending &&
      triggerRunMutation.variables?.recipeNames?.length === 1 &&
      triggerRunMutation.variables.recipeNames[0] === recipe.name) ||
    (trustVerifying &&
      quickRun?.mode === 'single' &&
      quickRun.recipe.id === recipe.id)

  return (
    <div className="space-y-6">
      <Breadcrumb>
        <BreadcrumbList>
          <BreadcrumbItem>
            <BreadcrumbLink asChild>
              <Link
                to="/autopkg/recipes"
                onClick={(e) => {
                  if (!confirmLoseChanges()) e.preventDefault()
                }}
              >
                Recipes
              </Link>
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbPage className="max-w-[min(100%,48ch)] truncate">
              {recipe.name}
            </BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-4 min-w-0">
          <SoftwareIcon
            name={pkgKey || recipe.name}
            displayName={meta?.displayName ?? null}
            iconName={recipeListIconName(meta?.iconName, recipe)}
            size="lg"
          />
          <div className={cn('min-w-0', munkiAccents.autopkg.pageTitle)}>
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="truncate text-2xl font-bold text-pretty sm:text-3xl">
                {meta?.displayName ?? recipe.name}
              </h1>
              <RecipeTrustStatusBadge status={recipe.trust_status} />
            </div>
            <p className="truncate font-mono text-xs text-muted-foreground sm:text-sm">
              {recipe.identifier}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 shrink-0">
          {canRun ? (
            <Button
              size="sm"
              disabled={runActionPending || !canTriggerRunRecipe(recipe)}
              title={
                canTriggerRunRecipe(recipe)
                  ? 'Run this recipe on GitHub Actions or a local Mac'
                  : 'Trust failed or pending — cannot run until resolved'
              }
              onClick={() => setQuickRun({ mode: 'single', recipe })}
            >
              {runThisPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden />
              ) : (
                <Play className="mr-2 h-4 w-4" aria-hidden />
              )}
              Run
            </Button>
          ) : null}
          {canEditRecipes && effectiveEditing && toolbar ? (
            <>
              <Button
                size="sm"
                onClick={toolbar.save}
                disabled={!toolbar.canSave}
              >
                {toolbar.isSaving ? (
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                ) : (
                  <Save className="h-4 w-4" aria-hidden />
                )}
                {toolbar.isSaving ? 'Saving…' : 'Save'}
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  if (!confirmLoseChanges()) return
                  handleCancelEdit()
                }}
                disabled={toolbar.isSaving}
              >
                <X className="h-4 w-4" />
                Cancel
              </Button>
            </>
          ) : canEditRecipes ? (
            <>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setEditing(true)}
              >
                <Pencil className="h-4 w-4" />
                Edit
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="text-destructive hover:bg-destructive/10 hover:text-destructive"
                disabled={!openDelete}
                onClick={() => openDelete?.()}
              >
                <Trash2 className="h-4 w-4" />
                Delete
              </Button>
            </>
          ) : null}
          {/* <Button variant="outline" size="sm" asChild>
            <Link
              to="/autopkg/recipes"
              onClick={(e) => {
                if (!confirmLoseChanges()) e.preventDefault()
              }}
            >
              <ArrowLeft className="mr-2 h-4 w-4" />
              Back to list
            </Link>
          </Button> */}
        </div>
      </div>

      <RecipeOverrideEditor
        key={editorKey}
        recipe={recipe}
        readOnly={!effectiveEditing}
        onDeleted={() => navigate('/autopkg/recipes')}
        onSaved={() => setEditing(false)}
        onToolbarApiChange={effectiveEditing ? setToolbar : undefined}
        onRegisterDelete={canEditRecipes ? registerDelete : undefined}
      />

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
    </div>
  )
}
