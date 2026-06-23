import { AlertTriangle, CheckCircle2, Clock, PauseCircle } from 'lucide-react'
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

export function DeploymentStatusBadge({
  deploymentStatus,
  shardPercent,
  isFirstProductionDeploy,
  inManifest,
}: {
  deploymentStatus: DeploymentStatus
  shardPercent: number | null
  isFirstProductionDeploy?: boolean
  inManifest?: boolean
}) {
  const manifestRisk =
    inManifest &&
    isFirstProductionDeploy &&
    (deploymentStatus === 'pending_rollout' || deploymentStatus === 'sharding')

  if (deploymentStatus === 'not_in_production') {
    return (
      <div className={cellClass}>
        <Badge
          variant="outline"
          className="w-fit gap-1 border-border text-muted-foreground"
        >
          Not in production
        </Badge>
      </div>
    )
  }

  if (deploymentStatus === 'fully_deployed') {
    return (
      <div className={cellClass}>
        <Badge
          variant="outline"
          className="w-fit gap-1 border-emerald-500/50 text-emerald-700 dark:border-emerald-500/40 dark:text-emerald-400"
        >
          <CheckCircle2 className="h-3 w-3" />
          Deployed
        </Badge>
      </div>
    )
  }

  if (deploymentStatus === 'pending_rollout') {
    return (
      <div className={cellClass}>
        <Badge
          variant="outline"
          className={cn(
            'w-fit gap-1 border-amber-500/70 text-amber-800 dark:border-amber-500/50 dark:text-amber-300',
            manifestRisk && manifestRiskBadgeClass,
          )}
          title={
            manifestRisk
              ? 'Net-new title in manifests before rollout started — high-shard devices may warn'
              : 'Awaiting approval to start production shard rollout'
          }
        >
          {manifestRisk ? (
            <AlertTriangle className="h-3 w-3" />
          ) : (
            <Clock className="h-3 w-3" />
          )}
          Awaiting rollout
        </Badge>
      </div>
    )
  }

  if (deploymentStatus === 'paused') {
    return (
      <div className={cellClass}>
        <Badge variant="secondary" className="w-fit gap-1">
          <PauseCircle className="h-3 w-3" />
          Paused
        </Badge>
      </div>
    )
  }

  const pct = shardPercent ?? 0
  return (
    <div className={cellClass}>
      <Badge
        variant="outline"
        className={cn(
          'w-fit gap-1 border-amber-500/70 text-amber-800 dark:border-amber-500/50 dark:text-amber-300',
          manifestRisk && manifestRiskBadgeClass,
        )}
        title={
          manifestRisk
            ? 'Net-new title in manifests while sharding — high-shard devices may warn until fully deployed'
            : `Sharding: ${pct}% of fleet eligible`
        }
      >
        {manifestRisk && <AlertTriangle className="h-3 w-3" />}
        Sharding {pct}%
      </Badge>
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
