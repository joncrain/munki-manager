import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, Loader2, Play, Save, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
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
  const [toolbar, setToolbar] = useState<RecipeOverrideToolbarApi | null>(null)

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
  }, [id])

  useEffect(() => {
    if (!canEditRecipes) setToolbar(null)
  }, [canEditRecipes])

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
            <BreadcrumbLink href="/autopkg/recipes">Recipes</BreadcrumbLink>
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
          {canEditRecipes && toolbar ? (
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
                {toolbar.isSaving ? 'Saving...' : 'Save'}
              </Button>
              <Button
                variant="destructive"
                size="icon"
                className="shrink-0"
                aria-label={`Delete override ${recipe.name}`}
                disabled={toolbar.isDeleting}
                onClick={toolbar.deleteRecipe}
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </>
          ) : null}
          <Button variant="outline" size="sm" asChild>
            <Link to="/autopkg/recipes">
              <ArrowLeft className="mr-2 h-4 w-4" />
              Back to list
            </Link>
          </Button>
        </div>
      </div>

      <RecipeOverrideEditor
        recipe={recipe}
        readOnly={!canEditRecipes}
        onDeleted={() => navigate('/autopkg/recipes')}
        onToolbarApiChange={canEditRecipes ? setToolbar : undefined}
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
