import { AlertTriangle, CheckCircle2, Clock, PauseCircle } from 'lucide-react'
import type { ReactNode } from 'react'
import { FilterBadge } from '@/components/filter-badge'
import { Badge } from '@/components/ui/badge'
import {
  manifestRiskBadgeClass,
  manifestRiskProgressClass,
} from '@/lib/shard-ui'
import { cn } from '@/lib/utils'

export type DeploymentStatus =
  | 'not_in_production'
  | 'pending_rollout'
  | 'sharding'
  | 'fully_deployed'
  | 'paused'

const cellClass =
  'flex min-h-[2.5rem] min-w-[8rem] flex-col justify-center gap-1'

function StatusBadge({
  onFilter,
  ariaLabel,
  title,
  className,
  children,
  variant = 'outline',
}: {
  onFilter?: () => void
  ariaLabel: string
  title?: string
  className?: string
  children: ReactNode
  variant?: 'outline' | 'secondary'
}) {
  if (onFilter) {
    return (
      <FilterBadge
        variant={variant}
        className={cn('w-fit gap-1', className)}
        onFilter={onFilter}
        ariaLabel={ariaLabel}
        title={title}
      >
        {children}
      </FilterBadge>
    )
  }

  return (
    <Badge
      variant={variant}
      className={cn('w-fit gap-1', className)}
      title={title}
    >
      {children}
    </Badge>
  )
}

export function DeploymentStatusBadge({
  deploymentStatus,
  shardPercent,
  isFirstProductionDeploy,
  inManifest,
  onFilter,
}: {
  deploymentStatus: DeploymentStatus
  shardPercent: number | null
  isFirstProductionDeploy?: boolean
  inManifest?: boolean
  onFilter?: () => void
}) {
  const manifestRisk =
    inManifest &&
    isFirstProductionDeploy &&
    (deploymentStatus === 'pending_rollout' || deploymentStatus === 'sharding')

  if (deploymentStatus === 'not_in_production') {
    return (
      <div className={cellClass}>
        <StatusBadge
          onFilter={onFilter}
          ariaLabel="Filter to not in production"
          className="border-border text-muted-foreground"
        >
          Not in production
        </StatusBadge>
      </div>
    )
  }

  if (deploymentStatus === 'fully_deployed') {
    return (
      <div className={cellClass}>
        <StatusBadge
          onFilter={onFilter}
          ariaLabel="Filter to fully deployed"
          className="border-emerald-500/50 text-emerald-700 dark:border-emerald-500/40 dark:text-emerald-400"
        >
          <CheckCircle2 className="h-3 w-3" />
          Deployed
        </StatusBadge>
      </div>
    )
  }

  if (deploymentStatus === 'pending_rollout') {
    return (
      <div className={cellClass}>
        <StatusBadge
          onFilter={onFilter}
          ariaLabel="Filter to awaiting rollout"
          title={
            manifestRisk
              ? 'Net-new title in manifests before rollout started — high-shard devices may warn'
              : 'Awaiting approval to start production shard rollout'
          }
          className={cn(
            'border-amber-500/70 text-amber-800 dark:border-amber-500/50 dark:text-amber-300',
            manifestRisk && manifestRiskBadgeClass,
          )}
        >
          {manifestRisk ? (
            <AlertTriangle className="h-3 w-3" />
          ) : (
            <Clock className="h-3 w-3" />
          )}
          Awaiting rollout
        </StatusBadge>
      </div>
    )
  }

  if (deploymentStatus === 'paused') {
    return (
      <div className={cellClass}>
        <StatusBadge
          onFilter={onFilter}
          ariaLabel="Filter to paused deployments"
          variant="secondary"
        >
          <PauseCircle className="h-3 w-3" />
          Paused
        </StatusBadge>
      </div>
    )
  }

  const pct = shardPercent ?? 0
  return (
    <div className={cellClass}>
      <StatusBadge
        onFilter={onFilter}
        ariaLabel="Filter to sharding deployments"
        title={
          manifestRisk
            ? 'Net-new title in manifests while sharding — high-shard devices may warn until fully deployed'
            : `Sharding: ${pct}% of fleet eligible`
        }
        className={cn(
          'border-amber-500/70 text-amber-800 dark:border-amber-500/50 dark:text-amber-300',
          manifestRisk && manifestRiskBadgeClass,
        )}
      >
        {manifestRisk && <AlertTriangle className="h-3 w-3" />}
        Sharding {pct}%
      </StatusBadge>
      <div className="h-1 w-full max-w-32 overflow-hidden rounded-full bg-muted">
        <div
          className={cn(
            'h-full rounded-full bg-amber-500 dark:bg-amber-400',
            manifestRisk && manifestRiskProgressClass,
          )}
          style={{ width: `${Math.min(100, Math.max(0, pct))}%` }}
        />
      </div>
    </div>
  )
}
