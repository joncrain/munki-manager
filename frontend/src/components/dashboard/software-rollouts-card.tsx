import { ArrowRight, Package, Percent, Timer } from 'lucide-react'
import type { ComponentType, ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { SoftwareAvatarCircles } from '@/components/software-avatar-circles'
import { SoftwareIcon } from '@/components/software-icon'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import type {
  PkgInfoPromotionQueueItemRead,
  PkgInfoShardQueueItemRead,
  PkgInfoSummary,
} from '@/lib/api'
import { formatDate } from '@/lib/format'
import { munkiAccents } from '@/lib/munki-accents'
import { cn } from '@/lib/utils'

function promotionIsEligible(row: PkgInfoPromotionQueueItemRead) {
  return row.leg_status !== 'waiting'
}

function sortedPromotions(rows: PkgInfoPromotionQueueItemRead[]) {
  return [...rows].sort((a, b) => {
    const aEligible = promotionIsEligible(a) ? 0 : 1
    const bEligible = promotionIsEligible(b) ? 0 : 1
    if (aEligible !== bEligible) return aEligible - bEligible
    return new Date(a.promote_at).getTime() - new Date(b.promote_at).getTime()
  })
}

function PanelShell({
  title,
  description,
  icon: Icon,
  children,
}: {
  title: string
  description: string
  icon: ComponentType<{ className?: string; 'aria-hidden'?: boolean }>
  children: ReactNode
}) {
  return (
    <section className="rounded-lg border bg-card/60 p-4">
      <div className="mb-3">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-foreground">
          <Icon className="size-4 shrink-0 text-muted-foreground" aria-hidden />
          {title}
        </h3>
        <p className="pt-0.5 text-xs text-muted-foreground">{description}</p>
      </div>
      {children}
    </section>
  )
}

function PromotionRow({ row }: { row: PkgInfoPromotionQueueItemRead }) {
  const title = row.display_name || row.name
  const eligible = promotionIsEligible(row)
  return (
    <li>
      <Link
        to={`/software/${row.id}`}
        className={cn(
          'flex flex-col gap-3 rounded-md border p-3 text-sm transition-colors md:flex-row md:items-center md:justify-between',
          munkiAccents.software.overviewRow,
        )}
      >
        <div className="flex min-w-0 items-start gap-3">
          <SoftwareIcon
            className="mt-0.5"
            name={row.name}
            displayName={row.display_name}
            size="sm"
          />
          <div className="min-w-0">
            <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
              <span className="truncate font-medium">{title}</span>
              <span className="font-mono text-xs text-muted-foreground">
                {row.version}
              </span>
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
              <span className="font-medium text-foreground/80">
                {row.channel_name}
              </span>
              <span className="rounded bg-muted px-1.5 py-0.5">
                {row.next_source_catalog}
              </span>
              <ArrowRight className="size-3" aria-hidden />
              <span className="rounded bg-muted px-1.5 py-0.5">
                {row.next_target_catalog}
              </span>
            </div>
          </div>
        </div>
        <Badge variant={eligible ? 'default' : 'secondary'}>
          {eligible
            ? 'Eligible next run'
            : `~${row.days_remaining}d · ${formatDate(row.promote_at)}`}
        </Badge>
      </Link>
    </li>
  )
}

function ShardRow({ row }: { row: PkgInfoShardQueueItemRead }) {
  const title = row.display_name || row.name
  return (
    <li>
      <Link
        to={`/software/${row.id}`}
        className={cn(
          'flex flex-col gap-2 rounded-md border p-3 text-sm transition-colors sm:flex-row sm:items-center sm:justify-between',
          munkiAccents.software.overviewRow,
        )}
      >
        <div className="min-w-0">
          <div className="truncate font-medium">
            {title}{' '}
            <span className="font-mono text-xs text-muted-foreground">
              {row.version}
            </span>
          </div>
          <div className="truncate text-xs text-muted-foreground">
            {row.deployment_status.replace('_', ' ')}
            {row.in_manifest && row.is_first_production_deploy
              ? ' · in manifest'
              : ''}
          </div>
        </div>
        {row.shard_percent != null ? (
          <Badge variant="outline">{row.shard_percent}%</Badge>
        ) : (
          <Badge variant="secondary">Awaiting approval</Badge>
        )}
      </Link>
    </li>
  )
}

export function SoftwareRolloutsCard({
  totalTitles,
  softwarePreviewItems,
  promotionQueue,
  promotionQueueLoading,
  shardQueue,
  shardQueueLoading,
  canSeeSoftware,
}: {
  totalTitles: number
  softwarePreviewItems: PkgInfoSummary[]
  promotionQueue: PkgInfoPromotionQueueItemRead[] | undefined
  promotionQueueLoading: boolean
  shardQueue: PkgInfoShardQueueItemRead[] | undefined
  shardQueueLoading: boolean
  canSeeSoftware: boolean
}) {
  const promotions = sortedPromotions(promotionQueue ?? [])
  return (
    <Card
      className={cn('flex h-full flex-col', munkiAccents.software.statCard)}
    >
      <CardHeader className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div className="space-y-1">
          <CardTitle className="flex items-center gap-2">
            <Package
              className={cn('size-5', munkiAccents.software.icon)}
              aria-hidden
            />
            Software
          </CardTitle>
          <CardDescription>
            Repository inventory, auto-promotion timing, and production rollout
            work.
          </CardDescription>
        </div>
        <Button variant="outline" size="sm" asChild>
          <Link to="/software">View all software</Link>
        </Button>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="flex flex-wrap items-center justify-between gap-4 rounded-lg border bg-background/50 p-4">
          <div>
            <div
              className="text-3xl font-bold"
              style={{ fontVariantNumeric: 'tabular-nums' }}
            >
              {totalTitles}
            </div>
            <p className="text-sm text-muted-foreground">
              Packages in the repository
            </p>
          </div>
          <SoftwareAvatarCircles
            packages={softwarePreviewItems}
            total={totalTitles}
            interactive={false}
          />
        </div>

        {canSeeSoftware ? (
          <div className="grid gap-4 lg:grid-cols-2">
            <PanelShell
              title="Auto-promotion"
              description="Channel path: dwell in progress, or next move on the next promotion run"
              icon={Timer}
            >
              {promotionQueueLoading ? (
                <p className="text-sm text-muted-foreground" aria-live="polite">
                  Loading…
                </p>
              ) : !promotions.length ? (
                <p className="text-sm text-muted-foreground">
                  No versions are in an active channel step (source catalog)
                  right now.
                </p>
              ) : (
                <ul className="max-h-[420px] space-y-2 overflow-y-auto overscroll-y-contain pr-0.5">
                  {promotions.map((row) => (
                    <PromotionRow key={row.id} row={row} />
                  ))}
                </ul>
              )}
            </PanelShell>

            <PanelShell
              title="Production rollouts"
              description="Shard rollout in progress or awaiting approval for net-new titles"
              icon={Percent}
            >
              {shardQueueLoading ? (
                <p className="text-sm text-muted-foreground">Loading…</p>
              ) : !shardQueue?.length ? (
                <p className="text-sm text-muted-foreground">
                  No active production shard rollouts.
                </p>
              ) : (
                <ul className="max-h-[420px] space-y-2 overflow-y-auto overscroll-y-contain pr-0.5">
                  {shardQueue.map((row) => (
                    <ShardRow key={row.id} row={row} />
                  ))}
                </ul>
              )}
            </PanelShell>
          </div>
        ) : null}
      </CardContent>
    </Card>
  )
}
