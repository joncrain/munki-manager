import { useQuery } from '@tanstack/react-query'
import { Copy, Loader2, Play } from 'lucide-react'
import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
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
  type AutoPkgRunRead,
  api,
  type RunResultRead,
  type UiSettingsRead,
} from '@/lib/api'
import { publicApiBaseUrl } from '@/lib/public-api-base'

/** Response from ``POST /autopkg/runs/verify-trust`` (live GitHub trust check). */
export type VerifyTrustForRunRecipeResult = {
  recipe_id: string
  name: string
  status: string
  diff?: Record<string, unknown> | null
  error?: string | null
}

export type VerifyTrustForRunResponse = {
  results: VerifyTrustForRunRecipeResult[]
  rate_limited: boolean
}

export function verifyTrustBeforeRun(
  recipeNames: string[] | null,
): Promise<VerifyTrustForRunResponse> {
  return api.post<VerifyTrustForRunResponse>('/autopkg/runs/verify-trust', {
    recipe_names: recipeNames,
  })
}

/** Trust failed / pending approval: excluded from runner config and cannot be selected. */
export function canTriggerRunRecipe(recipe: AutoPkgRecipeRead): boolean {
  return (
    recipe.trust_status !== 'failed' &&
    recipe.trust_status !== 'pending_approval'
  )
}

/** What the quick-run dialog should trigger (single recipe, all enabled, or table multi-select). */
export type RecipeQuickRunTarget =
  | { mode: 'single'; recipe: AutoPkgRecipeRead }
  | { mode: 'all' }
  | { mode: 'selected'; recipes: AutoPkgRecipeRead[] }

const LEGACY_RUNNER_STORAGE_KEY = 'automunki.autopkg_runner'
const LEGACY_RUNNER_LOCAL_DELIVERY_KEY = 'automunki.autopkg_local_delivery'

export const RUNNER_STORAGE_KEY = 'munki-manager.autopkg_runner'

/** When runner is local: ``manual`` = copy shell command; ``daemon`` = poll script picks up. */
export const RUNNER_LOCAL_DELIVERY_KEY = 'munki-manager.autopkg_local_delivery'

/** One-time migration of runner prefs to renamed localStorage keys; call once at app init. */
export function migrateAutopkgRunnerLocalStorageFromRebrand(): void {
  if (typeof window === 'undefined') return
  try {
    if (
      localStorage.getItem(RUNNER_STORAGE_KEY) == null &&
      localStorage.getItem(LEGACY_RUNNER_STORAGE_KEY) != null
    ) {
      localStorage.setItem(
        RUNNER_STORAGE_KEY,
        localStorage.getItem(LEGACY_RUNNER_STORAGE_KEY) as string,
      )
      localStorage.removeItem(LEGACY_RUNNER_STORAGE_KEY)
    }
    if (
      localStorage.getItem(RUNNER_LOCAL_DELIVERY_KEY) == null &&
      localStorage.getItem(LEGACY_RUNNER_LOCAL_DELIVERY_KEY) != null
    ) {
      localStorage.setItem(
        RUNNER_LOCAL_DELIVERY_KEY,
        localStorage.getItem(LEGACY_RUNNER_LOCAL_DELIVERY_KEY) as string,
      )
      localStorage.removeItem(LEGACY_RUNNER_LOCAL_DELIVERY_KEY)
    }
  } catch {
    /* private mode / quota */
  }
}

export type LocalDeliveryMode = 'manual' | 'daemon'

export function getLocalDeliveryMode(): LocalDeliveryMode {
  if (typeof window === 'undefined') return 'manual'
  return localStorage.getItem(RUNNER_LOCAL_DELIVERY_KEY) === 'daemon'
    ? 'daemon'
    : 'manual'
}

/** Safe for zsh/bash single-quoted strings */
export function shellSingleQuote(s: string): string {
  return `'${s.replace(/'/g, `'\\''`)}'`
}

export function getApiOrigin(): string {
  const fromEnv = publicApiBaseUrl()
  if (fromEnv) return fromEnv
  if (typeof window !== 'undefined') return window.location.origin
  return ''
}

/**
 * API origin for the copied `run_local_autopkg.sh` command. When the app is open on
 * the Vite dev server (port 3000) and `VITE_PUBLIC_API_URL` is unset, the shell
 * should talk to FastAPI on 8000 directly so it does not depend on the Vite proxy.
 */
export function getLocalRunnerApiOrigin(): string {
  const fromEnv = publicApiBaseUrl()
  if (fromEnv) return fromEnv
  if (typeof window === 'undefined') return ''
  const { origin, port, hostname, protocol } = window.location
  if (hostname === 'localhost' && port === '3000') {
    return `${protocol}//${hostname}:8000`
  }
  return origin
}

/** Current browser session JWT (FastAPI-Users), when logged in. */
function getClientAccessToken(): string | null {
  if (typeof window === 'undefined') return null
  try {
    const t = localStorage.getItem('token')
    if (t == null) return null
    const s = t.trim()
    return s.length > 0 ? s : null
  } catch {
    return null
  }
}

/** Command to run from the munki-manager repo root (see AutoPkg/scripts/run_local_autopkg.sh) */
export function buildLocalRunnerShellCommand(run: AutoPkgRunRead): {
  command: string
  usedClientAccessToken: boolean
} {
  const origin = getLocalRunnerApiOrigin()
  const originArg = origin || '<your-api-origin>'
  let line = `./AutoPkg/scripts/run_local_autopkg.sh --backend-url ${shellSingleQuote(originArg)} --run-id ${run.id}`
  if (run.recipe_filter?.length) {
    line += ` --recipes ${shellSingleQuote(run.recipe_filter.join(','))}`
  }
  const access = getClientAccessToken()
  const usedClientAccessToken = access != null
  if (access != null) {
    line += ` --token ${shellSingleQuote(access)}`
  }
  return { command: line, usedClientAccessToken }
}

/** Sonner id for the manual local-runner command toast; dismissed after Copy. */
export const LOCAL_RUNNER_MANUAL_TOAST_ID =
  'munki-manager.autopkg.local-runner-manual'

export function LocalRunnerToastBody({
  cmd,
  usedClientAccessToken,
  dismissToastId,
}: {
  cmd: string
  usedClientAccessToken: boolean
  /** When set, ``toast.dismiss`` this id after a successful copy (closes the parent toast). */
  dismissToastId?: string
}) {
  return (
    <div className="mt-2 space-y-2">
      <pre className="max-h-40 overflow-auto break-all rounded-md border bg-muted/50 p-2 text-left font-mono text-xs whitespace-pre-wrap">
        {cmd}
      </pre>
      <div className="flex flex-wrap items-center gap-2">
        <Button
          type="button"
          size="sm"
          variant="secondary"
          className="shrink-0"
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(cmd)
              if (dismissToastId) {
                toast.dismiss(dismissToastId)
              }
              toast.success('Copied to clipboard', { duration: 2500 })
            } catch {
              toast.error('Could not copy to clipboard')
            }
          }}
        >
          <Copy className="mr-1.5 h-3.5 w-3.5" />
          Copy command
        </Button>
      </div>
      {usedClientAccessToken ? (
        <p className="text-muted-foreground text-xs leading-snug">
          The command includes <code className="text-xs">--token</code> with
          your current session (it expires; treat it like a password and mind
          shell history). For automation, use{' '}
          <code className="text-xs">LOCAL_RUNNER_TOKEN</code> in the repo{' '}
          <code className="text-xs">.env</code> instead. See{' '}
          <code className="text-xs">docs/local-autopkg-runner.md</code>.
        </p>
      ) : (
        <p className="text-muted-foreground text-xs leading-snug">
          Put <code className="text-xs">LOCAL_RUNNER_TOKEN</code> in the repo
          root <code className="text-xs">.env</code> (same as the server) and
          the script will use it. Otherwise set{' '}
          <code className="text-xs">AUTOMUNKI_API_TOKEN</code> or{' '}
          <code className="text-xs">--token</code> (e.g. your JWT from the
          browser). See{' '}
          <code className="text-xs">docs/local-autopkg-runner.md</code>.
        </p>
      )}
    </div>
  )
}

export function LocalDaemonToastBody() {
  return (
    <p className="mt-2 text-muted-foreground text-xs leading-snug">
      If <code className="text-xs">poll_local_autopkg.sh</code> is running with{' '}
      <code className="text-xs">LOCAL_RUNNER_TOKEN</code>, it will claim and run
      this automatically. See{' '}
      <code className="text-xs">docs/local-autopkg-runner.md</code>.
    </p>
  )
}

/** Call after a successful local run registration; reads delivery mode from localStorage. */
export function TrustVerifyFailureDialog({
  open,
  onOpenChange,
  verify,
  onContinue,
  onStop,
  isContinuing,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  verify: VerifyTrustForRunResponse
  onContinue: () => void
  onStop: () => void
  isContinuing: boolean
}) {
  const failed = verify.results.filter((r) => r.status !== 'verified')
  const okCount = verify.results.filter((r) => r.status === 'verified').length

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Trust check did not pass for every recipe</DialogTitle>
          <DialogDescription>
            We compared stored trust to live content on GitHub. Some recipes
            failed verification or could not be checked. You can stop and fix
            trust on the Approvals or recipe pages, or continue with only the
            recipes that verified.
          </DialogDescription>
        </DialogHeader>
        {verify.rate_limited && (
          <p className="rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm">
            GitHub rate limit was hit partway through; only some recipes were
            checked. Try again later for a full run.
          </p>
        )}
        <ul className="max-h-48 space-y-2 overflow-y-auto rounded-md border p-3 text-sm">
          {failed.map((r) => (
            <li key={r.recipe_id}>
              <span className="font-medium">{r.name}</span>
              <span className="text-muted-foreground">
                {' '}
                — {r.status === 'failed' ? 'hash mismatch' : r.error || 'error'}
              </span>
            </li>
          ))}
        </ul>
        <p className="text-muted-foreground text-xs">
          {okCount} recipe{okCount === 1 ? '' : 's'} verified and can run.
        </p>
        <DialogFooter className="gap-2 sm:gap-0">
          <Button variant="outline" onClick={onStop} disabled={isContinuing}>
            Stop and fix trust
          </Button>
          <Button onClick={onContinue} disabled={isContinuing || okCount === 0}>
            {isContinuing ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Starting…
              </>
            ) : (
              `Continue without ${failed.length} recipe${failed.length === 1 ? '' : 's'}`
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function toastLocalRunRegistered(run: AutoPkgRunRead) {
  if (getLocalDeliveryMode() === 'daemon') {
    toast.success('Local run queued', {
      description: <LocalDaemonToastBody />,
      duration: 14_000,
      closeButton: true,
    })
    return
  }
  const { command: cmd, usedClientAccessToken } =
    buildLocalRunnerShellCommand(run)
  toast.success('Local run registered — run from your clone', {
    id: LOCAL_RUNNER_MANUAL_TOAST_ID,
    description: (
      <LocalRunnerToastBody
        cmd={cmd}
        usedClientAccessToken={usedClientAccessToken}
        dismissToastId={LOCAL_RUNNER_MANUAL_TOAST_ID}
      />
    ),
    duration: Infinity,
    closeButton: true,
  })
}

export function QuickRunDialog({
  open,
  onOpenChange,
  target,
  isPending,
  trustVerifying = false,
  onConfirm,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  target: RecipeQuickRunTarget | null
  isPending: boolean
  /** While comparing trust to GitHub (before the run is registered). */
  trustVerifying?: boolean
  /** ``recipeNames`` null = all enabled recipes; otherwise explicit list for the run. */
  onConfirm: (
    runner: 'github' | 'local',
    recipeNames: string[] | null,
  ) => void | Promise<void>
}) {
  const [runnerChoice, setRunnerChoice] = useState<
    'github' | 'local-manual' | 'local-daemon'
  >('github')

  const { data: uiSettings } = useQuery({
    queryKey: ['settings', 'ui'],
    queryFn: () => api.get<UiSettingsRead>('/settings/ui'),
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

  const singleBlocked =
    target?.mode === 'single' && !canTriggerRunRecipe(target.recipe)

  const blockedInSelection =
    target?.mode === 'selected'
      ? target.recipes.filter((r) => !canTriggerRunRecipe(r))
      : []

  const cannotRun = singleBlocked || blockedInSelection.length > 0

  const handleRun = async () => {
    if (!target || cannotRun) return
    const apiRunner = runnerChoice === 'github' ? 'github' : 'local'
    localStorage.setItem(RUNNER_STORAGE_KEY, apiRunner)
    if (apiRunner === 'local') {
      localStorage.setItem(
        RUNNER_LOCAL_DELIVERY_KEY,
        runnerChoice === 'local-daemon' ? 'daemon' : 'manual',
      )
    }
    const recipeNames =
      target.mode === 'all'
        ? null
        : target.mode === 'single'
          ? [target.recipe.name]
          : target.recipes.map((r) => r.name)
    await Promise.resolve(onConfirm(apiRunner, recipeNames))
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>
            {target?.mode === 'single'
              ? `Run recipe: ${target.recipe.name}`
              : target?.mode === 'selected'
                ? `Run ${target.recipes.length} selected recipe${target.recipes.length === 1 ? '' : 's'}`
                : 'Run all enabled recipes'}
          </DialogTitle>
          <DialogDescription>
            {target?.mode === 'single' ? (
              <>
                Choose whether AutoPkg runs on GitHub Actions or locally on a
                Mac (see{' '}
                <code className="text-xs">docs/local-autopkg-runner.md</code>).
              </>
            ) : target?.mode === 'selected' ? (
              <>
                Runs only the recipes you selected in the table (not necessarily
                every enabled recipe). Choose GitHub Actions or a local Mac
                runner.
              </>
            ) : (
              <>
                Triggers AutoPkg for every <strong>enabled</strong> recipe
                override, same as choosing no recipes on the Runs page. Recipes
                with failed or pending trust are skipped. Trust is re-checked
                against GitHub before starting.
              </>
            )}
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-2 py-2">
          <Label htmlFor="quick-run-runner">Runner</Label>
          <Select
            value={runnerChoice}
            onValueChange={(v) =>
              setRunnerChoice(v as 'github' | 'local-manual' | 'local-daemon')
            }
          >
            <SelectTrigger id="quick-run-runner" className="w-full">
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
          {runnerChoice === 'local-manual' && (
            <p className="text-xs text-muted-foreground">
              After confirming, copy the shell command from the toast and run it
              in your clone.
            </p>
          )}
          {runnerChoice === 'local-daemon' && (
            <p className="text-xs text-muted-foreground">
              Use <code className="text-xs">poll_local_autopkg.sh</code> with{' '}
              <code className="text-xs">LOCAL_RUNNER_TOKEN</code> on the Mac
              that runs AutoPkg.
            </p>
          )}
        </div>

        {singleBlocked && (
          <p className="rounded-md border border-dashed bg-muted/40 px-3 py-2 text-sm text-muted-foreground">
            This recipe cannot run until trust is verified or approved (failed
            or pending).
          </p>
        )}

        {blockedInSelection.length > 0 && (
          <p className="rounded-md border border-dashed bg-muted/40 px-3 py-2 text-sm text-muted-foreground">
            Cannot run while selection includes recipes with failed or pending
            trust:{' '}
            <span className="font-medium">
              {blockedInSelection.map((r) => r.name).join(', ')}
            </span>
          </p>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={() => void handleRun()}
            disabled={isPending || cannotRun || trustVerifying}
          >
            {trustVerifying || isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Play className="h-4 w-4" />
            )}
            {trustVerifying
              ? 'Verifying trust…'
              : isPending
                ? 'Starting…'
                : target?.mode === 'single'
                  ? 'Run'
                  : target?.mode === 'selected'
                    ? `Run ${target.recipes.length} selected`
                    : 'Run all enabled'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** Munki pkginfo name for linking an AutoPkg run result to software detail. */
export function runResultPkginfoKey(result: RunResultRead): string {
  const path = result.imported_pkginfo_path?.trim()
  let stem = ''
  if (path) {
    const base = path.split(/[/\\]/).pop() ?? path
    stem = base.replace(/\.plist$/i, '')
  }
  if (!stem) {
    stem = result.recipe_name
      .replace(/\.munki\.recipe$/i, '')
      .replace(/\.recipe$/i, '')
  }
  const version = result.imported_version?.trim()
  if (version && stem.endsWith(`-${version}`)) {
    return stem.slice(0, -(version.length + 1))
  }
  return stem
}
