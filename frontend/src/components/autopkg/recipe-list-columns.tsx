import type { ColumnDef, VisibilityState } from '@tanstack/react-table'
import {
  Loader2,
  Play,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  ShieldQuestion,
  Trash2,
} from 'lucide-react'
import { SoftwareIcon } from '@/components/software-icon'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import type { PkginfoItemMeta } from '@/hooks/use-pkginfo-display-labels'
import type { AutoPkgRecipeRead } from '@/lib/api'
import {
  pkginfoCatalogsFromRecipe,
  recipeInputName,
  recipeListIconName,
  recipePkginfoKey,
} from '@/lib/autopkg-recipe'
import { canTriggerRunRecipe } from '@/lib/autopkg-run'
import { formatDateTime } from '@/lib/format'

function trustStatusBadge(status: string) {
  switch (status) {
    case 'verified':
      return (
        <Badge
          variant="default"
          className="bg-gruvbox-green text-primary-foreground hover:bg-gruvbox-green/90"
        >
          <ShieldCheck className="mr-1 h-3 w-3" />
          Verified
        </Badge>
      )
    case 'failed':
      return (
        <Badge variant="destructive">
          <ShieldAlert className="mr-1 h-3 w-3" />
          Failed
        </Badge>
      )
    case 'pending_approval':
      return (
        <Badge
          variant="default"
          className="bg-gruvbox-yellow text-primary-foreground hover:bg-gruvbox-yellow/90"
        >
          <ShieldAlert className="mr-1 h-3 w-3" />
          Pending
        </Badge>
      )
    default:
      return (
        <Badge variant="secondary">
          <ShieldQuestion className="mr-1 h-3 w-3" />
          Unknown
        </Badge>
      )
  }
}

export interface RecipeListColumnOptions {
  canEditRecipes: boolean
  canRun: boolean
  canVerifyTrust: boolean
}

export function recipeListColumns(
  pkgMeta: Record<string, PkginfoItemMeta> | undefined,
  onToggleEnabled: (id: string, enabled: boolean) => void,
  onToggleAutoPromote: (id: string, auto: boolean) => void,
  onEdit: (recipe: AutoPkgRecipeRead) => void,
  onRunRecipe: (recipe: AutoPkgRecipeRead) => void,
  onVerifyTrust: (id: string) => void,
  onDelete: (recipe: AutoPkgRecipeRead) => void,
  verifyingTrustId: string | null,
  pendingRunRecipeName: string | null,
  isRunPending: boolean,
  opts: RecipeListColumnOptions,
): ColumnDef<AutoPkgRecipeRead>[] {
  return [
    {
      id: 'item_icon',
      header: 'Icon',
      size: 44,
      cell: ({ row }) => {
        const key = recipePkginfoKey(row.original)
        const meta = pkgMeta?.[key]
        return (
          <div className="flex">
            <SoftwareIcon
              name={key}
              iconName={recipeListIconName(meta?.iconName, row.original)}
              displayName={meta?.displayName ?? key}
              size="sm"
            />
          </div>
        )
      },
    },
    {
      id: 'pkg_display_name',
      header: 'Display Name',
      accessorFn: (row) => pkgMeta?.[recipePkginfoKey(row)]?.displayName ?? '',
      cell: ({ row }) => {
        const key = recipePkginfoKey(row.original)
        const label = pkgMeta?.[key]?.displayName
        return (
          <button
            type="button"
            className="max-w-[min(280px,28vw)] truncate text-left text-sm font-medium hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm"
            onClick={() => onEdit(row.original)}
            title={label ?? undefined}
          >
            {label ?? '—'}
          </button>
        )
      },
    },
    {
      accessorKey: 'name',
      header: 'Name',
      cell: ({ row }) => (
        <button
          type="button"
          className="flex items-center gap-2 text-left hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm"
          onClick={() => onEdit(row.original)}
        >
          <span className="font-medium">{row.original.name}</span>
          <Badge variant="outline" className="text-xs">
            Override
          </Badge>
        </button>
      ),
    },
    {
      accessorKey: 'identifier',
      header: 'Identifier',
      cell: ({ row }) => (
        <span className="truncate font-mono text-sm text-muted-foreground">
          {row.original.identifier}
        </span>
      ),
    },
    {
      id: 'input_name',
      accessorFn: (row) => recipeInputName(row),
      header: 'Input NAME',
      cell: ({ row }) => {
        const n = recipeInputName(row.original)
        return n ? (
          <span className="truncate text-sm" title={n}>
            {n}
          </span>
        ) : (
          '—'
        )
      },
    },
    {
      accessorKey: 'parent_recipe',
      header: 'Parent recipe',
      cell: ({ row }) => {
        const p = row.original.parent_recipe
        if (!p) return '—'
        return (
          <span
            className="max-w-[200px] truncate font-mono text-xs text-muted-foreground"
            title={p}
          >
            {p}
          </span>
        )
      },
    },
    {
      accessorKey: 'source_repo_full_name',
      header: 'Repo',
      cell: ({ row }) => {
        const repo = row.original.source_repo_full_name
        if (!repo) return '—'
        return (
          <a
            href={`https://github.com/${repo}`}
            target="_blank"
            rel="noopener noreferrer"
            className="block max-w-[160px] truncate font-mono text-xs text-primary underline-offset-4 hover:underline"
            title={repo}
          >
            {repo}
          </a>
        )
      },
    },
    {
      accessorKey: 'trust_status',
      header: 'Trust',
      cell: ({ row }) => {
        const isVerifying = verifyingTrustId === row.original.id
        return (
          <div className="flex items-center gap-1">
            {trustStatusBadge(row.original.trust_status)}
            {opts.canVerifyTrust && (
              <Button
                variant="ghost"
                size="sm"
                className="h-6 w-6 p-0"
                aria-label={`Verify trust for ${row.original.name}`}
                disabled={isVerifying}
                onClick={() => onVerifyTrust(row.original.id)}
              >
                <RefreshCw
                  className={`h-3 w-3 ${isVerifying ? 'animate-spin' : ''}`}
                />
              </Button>
            )}
          </div>
        )
      },
    },
    {
      accessorKey: 'is_enabled',
      header: 'Enabled',
      cell: ({ row }) =>
        opts.canEditRecipes ? (
          <Switch
            checked={row.original.is_enabled}
            onCheckedChange={(checked) =>
              onToggleEnabled(row.original.id, checked)
            }
            aria-label={`Toggle ${row.original.name} enabled`}
          />
        ) : (
          <span className="text-sm text-muted-foreground">
            {row.original.is_enabled ? 'Yes' : 'No'}
          </span>
        ),
    },
    {
      accessorKey: 'auto_promote',
      header: 'Auto Promote',
      cell: ({ row }) =>
        opts.canEditRecipes ? (
          <Switch
            checked={row.original.auto_promote}
            onCheckedChange={(checked) =>
              onToggleAutoPromote(row.original.id, checked)
            }
            aria-label={`Toggle ${row.original.name} auto-promote`}
          />
        ) : (
          <span className="text-sm text-muted-foreground">
            {row.original.auto_promote ? 'Yes' : 'No'}
          </span>
        ),
    },
    {
      id: 'pkginfo_catalogs',
      header: 'Catalogs',
      cell: ({ row }) => {
        const cats = pkginfoCatalogsFromRecipe(row.original)
        if (cats.length === 0) return '—'
        return (
          <div className="flex flex-wrap gap-1">
            {cats.map((c) => (
              <Badge key={c} variant="secondary">
                {c}
              </Badge>
            ))}
          </div>
        )
      },
    },
    {
      accessorKey: 'last_run_status',
      header: 'Run status',
      cell: ({ row }) => {
        const st = row.original.last_run_status
        if (!st) return '—'
        const ok = ['success', 'imported', 'no_change'].includes(st)
        return <Badge variant={ok ? 'default' : 'destructive'}>{st}</Badge>
      },
    },
    {
      accessorKey: 'last_run_at',
      header: 'Last run at',
      cell: ({ row }) => {
        const at = row.original.last_run_at
        if (!at) return '—'
        return (
          <span
            suppressHydrationWarning
            className="whitespace-nowrap text-sm text-muted-foreground"
          >
            {formatDateTime(at)}
          </span>
        )
      },
    },
    {
      accessorKey: 'updated_at',
      header: 'Updated',
      cell: ({ row }) => (
        <span
          suppressHydrationWarning
          className="whitespace-nowrap text-sm text-muted-foreground"
        >
          {formatDateTime(row.original.updated_at)}
        </span>
      ),
    },
    {
      id: 'run',
      header: '',
      enableHiding: false,
      size: 48,
      cell: ({ row }) => {
        if (!opts.canRun) return null
        const r = row.original
        const runnable = canTriggerRunRecipe(r)
        const isThisPending =
          pendingRunRecipeName !== null && pendingRunRecipeName === r.name
        return (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-8 w-8 p-0"
            aria-label={`Run recipe ${r.name}`}
            title={
              runnable
                ? 'Run this recipe'
                : 'Trust failed or pending — cannot run until resolved'
            }
            disabled={!runnable || isRunPending}
            onClick={(e) => {
              e.stopPropagation()
              onRunRecipe(r)
            }}
          >
            {isThisPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Play className="h-4 w-4" />
            )}
          </Button>
        )
      },
    },
    {
      id: 'actions',
      header: '',
      enableHiding: false,
      cell: ({ row }) =>
        opts.canEditRecipes ? (
          <Button
            variant="ghost"
            size="sm"
            className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive"
            aria-label={`Delete override ${row.original.name}`}
            onClick={(e) => {
              e.stopPropagation()
              onDelete(row.original)
            }}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        ) : null,
    },
  ]
}

export const recipeListDefaultColumnVisibility: VisibilityState = {
  select: true,
  item_icon: true,
  pkg_display_name: true,
  name: false,
  identifier: false,
  input_name: false,
  parent_recipe: false,
  source_repo_full_name: false,
  trust_status: true,
  is_enabled: true,
  auto_promote: false,
  pkginfo_catalogs: true,
  last_run_status: true,
  last_run_at: true,
  updated_at: false,
}
