import { AlertTriangle, CheckCircle2, Clock, PauseCircle } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

export type DeploymentStatus =
  | 'not_in_production'
  | 'pending_rollout'
  | 'sharding'
  | 'fully_deployed'
  | 'paused'

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
    return <span className="text-sm text-muted-foreground">—</span>
  }

  if (deploymentStatus === 'fully_deployed') {
    return (
      <Badge
        variant="outline"
        className="gap-1 border-emerald-500/50 text-emerald-700"
      >
        <CheckCircle2 className="h-3 w-3" />
        Deployed
      </Badge>
    )
  }

  if (deploymentStatus === 'pending_rollout') {
    return (
      <Badge
        variant="outline"
        className={cn(
          'gap-1 border-amber-500 text-amber-700',
          manifestRisk && 'border-red-500 text-red-700',
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
    )
  }

  if (deploymentStatus === 'paused') {
    return (
      <Badge variant="secondary" className="gap-1">
        <PauseCircle className="h-3 w-3" />
        Paused
      </Badge>
    )
  }

  const pct = shardPercent ?? 0
  return (
    <div className="flex min-w-[7rem] flex-col gap-1">
      <Badge
        variant="outline"
        className={cn(
          'gap-1 border-amber-500/70 text-amber-800',
          manifestRisk && 'border-red-500 text-red-700',
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
      <div className="h-1 w-full overflow-hidden rounded-full bg-muted">
        <div
          className={cn(
            'h-full rounded-full bg-amber-500 transition-all',
            manifestRisk && 'bg-red-500',
          )}
          style={{ width: `${Math.min(100, Math.max(0, pct))}%` }}
        />
      </div>
    </div>
  )
}
