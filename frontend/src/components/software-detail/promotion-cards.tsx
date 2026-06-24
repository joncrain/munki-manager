import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { CatalogEditor } from '@/components/software-detail/catalog-editor'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'
import { Slider } from '@/components/ui/slider'
import { Switch } from '@/components/ui/switch'
import {
  api,
  type PkgInfoPromotionStatusRead,
  type PkgInfoShardStatusRead,
  type PromotionChannelRead,
} from '@/lib/api'
import { formatDate } from '@/lib/format'
import { manifestRiskAlertClass } from '@/lib/shard-ui'
import { cn } from '@/lib/utils'

export function CatalogsPromotionCard({
  pkgId,
  canEdit,
  catalogNames,
  autoPromote,
  promotionChannelId,
}: {
  pkgId: string
  canEdit: boolean
  catalogNames: string[]
  autoPromote: boolean
  promotionChannelId: string | null
}) {
  const queryClient = useQueryClient()
  const { data: st, isLoading: stLoading } = useQuery({
    queryKey: ['pkginfo', pkgId, 'promotion-status'],
    queryFn: () =>
      api.get<PkgInfoPromotionStatusRead>(`/pkginfo/${pkgId}/promotion-status`),
    enabled: autoPromote,
  })
  const { data: promotionChannels } = useQuery({
    queryKey: ['promotion-channels'],
    queryFn: () => api.get<PromotionChannelRead[]>('/promotion-channels'),
    enabled: autoPromote && canEdit,
  })
  const patch = useMutation({
    mutationFn: (body: {
      auto_promote?: boolean
      promotion_channel_id?: string | null
    }) => api.put(`/pkginfo/${pkgId}`, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['pkginfo', pkgId] })
      void queryClient.invalidateQueries({
        queryKey: ['pkginfo', pkgId, 'promotion-status'],
      })
    },
    onError: (e: Error) => toast.error(e.message),
  })
  const busy = patch.isPending
  const noneVal = '__none__'
  const chValue = promotionChannelId ?? noneVal
  const orphanPchId =
    promotionChannelId &&
    !(promotionChannels ?? []).some((c) => c.id === promotionChannelId)
      ? promotionChannelId
      : null

  return (
    <Card>
      <CardHeader className="flex flex-col gap-3 space-y-0 pb-3 sm:flex-row sm:items-center sm:justify-between sm:space-y-0">
        <CardTitle>Catalogs &amp; Promotion</CardTitle>
        <div className="flex shrink-0 items-center justify-end gap-2 sm:ml-auto">
          <Switch
            id={`pkg-ap-header-${pkgId}`}
            checked={autoPromote}
            disabled={!canEdit || busy}
            onCheckedChange={(v) => patch.mutate({ auto_promote: v })}
          />
          <Label
            htmlFor={`pkg-ap-header-${pkgId}`}
            className={cn(
              'cursor-pointer text-sm',
              !canEdit && 'cursor-default',
            )}
          >
            Auto-promote
          </Label>
        </div>
      </CardHeader>
      <CardContent className="space-y-0">
        <CatalogEditor
          pkgId={pkgId}
          catalogNames={catalogNames}
          readOnly={!canEdit}
        />
        {autoPromote && (
          <>
            <Separator className="my-6" />
            {stLoading ? (
              <p className="text-sm text-muted-foreground" aria-live="polite">
                Loading promotion…
              </p>
            ) : st ? (
              <div className="space-y-4">
                {canEdit && (
                  <div className="max-w-md space-y-1.5">
                    <Label className="text-xs" htmlFor={`pkg-pch-${pkgId}`}>
                      Promotion channel
                    </Label>
                    <Select
                      value={chValue}
                      onValueChange={(v) => {
                        const next = v === noneVal ? null : v
                        patch.mutate({ promotion_channel_id: next })
                      }}
                      disabled={busy}
                    >
                      <SelectTrigger
                        id={`pkg-pch-${pkgId}`}
                        className="w-full text-sm"
                      >
                        <SelectValue placeholder="None" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value={noneVal}>None</SelectItem>
                        {orphanPchId ? (
                          <SelectItem value={orphanPchId}>
                            Current (not in list)
                          </SelectItem>
                        ) : null}
                        {(promotionChannels ?? [])
                          .slice()
                          .sort((a, b) => a.name.localeCompare(b.name))
                          .map((ch) => (
                            <SelectItem key={ch.id} value={ch.id}>
                              {ch.name}
                              {ch.steps.length
                                ? ` (${ch.steps.length} step${
                                    ch.steps.length === 1 ? '' : 's'
                                  })`
                                : ''}
                            </SelectItem>
                          ))}
                      </SelectContent>
                    </Select>
                  </div>
                )}
                {!canEdit && st.channel_name ? (
                  <p className="text-xs text-muted-foreground">
                    Channel: {st.channel_name}
                  </p>
                ) : null}
                {st.catalog_memberships.length > 0 && (
                  <p className="text-xs text-muted-foreground break-words">
                    {st.catalog_memberships
                      .map(
                        (m) =>
                          `${m.catalog_name} (${formatDate(m.entered_at)})`,
                      )
                      .join(' · ')}
                  </p>
                )}
                {st.legs.length > 0 ? (
                  <ul className="list-none space-y-1.5 text-sm text-pretty text-foreground">
                    {st.legs.map((leg) => (
                      <li key={leg.step_order}>
                        <span className="text-muted-foreground">
                          {leg.step_order}.{' '}
                        </span>
                        {leg.source_catalog_name} → {leg.target_catalog_name}
                        {leg.dwell_days > 0
                          ? ` · ${leg.dwell_days}d from ${formatDate(leg.dwell_clock_start_at)}`
                          : ''}
                        {' · '}
                        <span className="text-muted-foreground">
                          {leg.status === 'waiting'
                            ? `~${leg.days_remaining}d until ${formatDate(leg.promote_at)}`
                            : 'Next run'}
                        </span>
                      </li>
                    ))}
                  </ul>
                ) : st.summary ? (
                  <p className="text-sm text-muted-foreground">{st.summary}</p>
                ) : null}
              </div>
            ) : null}
          </>
        )}
      </CardContent>
    </Card>
  )
}

export function ProductionRolloutCard({
  pkgId,
  canEdit,
}: {
  pkgId: string
  canEdit: boolean
}) {
  const queryClient = useQueryClient()
  const { data: st, isLoading } = useQuery({
    queryKey: ['pkginfo', pkgId, 'shard-status'],
    queryFn: () =>
      api.get<PkgInfoShardStatusRead>(`/pkginfo/${pkgId}/shard-status`),
  })

  const [overrideEnabled, setOverrideEnabled] = useState(false)
  const [overrideValue, setOverrideValue] = useState(25)

  useEffect(() => {
    if (!st) return
    const hasOverride = st.shard_percent_override != null
    setOverrideEnabled(hasOverride)
    setOverrideValue(
      st.shard_percent_override ??
        st.shard_percent ??
        st.scheduled_shard_percent ??
        25,
    )
  }, [st])

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['pkginfo', pkgId] })
    void queryClient.invalidateQueries({
      queryKey: ['pkginfo', pkgId, 'shard-status'],
    })
    void queryClient.invalidateQueries({ queryKey: ['pkginfo'] })
    void queryClient.invalidateQueries({ queryKey: ['pkginfo', 'shard-queue'] })
  }

  const startMut = useMutation({
    mutationFn: () => api.post(`/pkginfo/${pkgId}/shard/start`, {}),
    onSuccess: () => {
      toast.success('Production rollout started')
      invalidate()
    },
    onError: (e: Error) => toast.error(e.message),
  })
  const pauseMut = useMutation({
    mutationFn: () => api.post(`/pkginfo/${pkgId}/shard/pause`, {}),
    onSuccess: () => {
      toast.success('Production rollout paused')
      invalidate()
    },
    onError: (e: Error) => toast.error(e.message),
  })
  const completeMut = useMutation({
    mutationFn: () => api.post(`/pkginfo/${pkgId}/shard/complete`, {}),
    onSuccess: () => {
      toast.success('Production rollout completed')
      invalidate()
    },
    onError: (e: Error) => toast.error(e.message),
  })
  const overrideMut = useMutation({
    mutationFn: (shard_percent: number | null) =>
      api.put<PkgInfoShardStatusRead>(`/pkginfo/${pkgId}/shard/override`, {
        shard_percent,
      }),
    onSuccess: () => {
      toast.success('Shard override updated')
      invalidate()
    },
    onError: (e: Error) => toast.error(e.message),
  })

  const busy =
    startMut.isPending ||
    pauseMut.isPending ||
    completeMut.isPending ||
    overrideMut.isPending
  const canStart =
    st?.deployment_status === 'pending_rollout' ||
    st?.shard_rollout_status === 'pending_approval'
  const canPause = st?.deployment_status === 'sharding'
  const canComplete =
    st?.deployment_status === 'sharding' ||
    st?.deployment_status === 'paused' ||
    st?.deployment_status === 'pending_rollout'

  const showShardOverride =
    canEdit &&
    st &&
    st.deployment_status !== 'not_in_production' &&
    st.deployment_status !== 'pending_rollout' &&
    st.deployment_status !== 'fully_deployed'

  return (
    <Card>
      <CardHeader className="flex flex-col gap-3 space-y-0 pb-3 sm:flex-row sm:items-center sm:justify-between sm:space-y-0">
        <CardTitle>Production rollout</CardTitle>
        {canEdit && st?.active ? (
          <div className="flex flex-wrap gap-2">
            {canStart ? (
              <Button
                size="sm"
                disabled={busy}
                onClick={() => startMut.mutate()}
              >
                Start rollout
              </Button>
            ) : null}
            {canPause ? (
              <Button
                size="sm"
                variant="outline"
                disabled={busy}
                onClick={() => pauseMut.mutate()}
              >
                Pause
              </Button>
            ) : null}
            {canComplete ? (
              <Button
                size="sm"
                variant="secondary"
                disabled={busy}
                onClick={() => completeMut.mutate()}
              >
                Force complete
              </Button>
            ) : null}
          </div>
        ) : null}
      </CardHeader>
      <CardContent className="space-y-3">
        {isLoading ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : st ? (
          <>
            {st.manifest_warning ? (
              <div className={manifestRiskAlertClass}>
                Net-new title referenced in manifests while not fully deployed.
                High-shard devices may report missing catalog items until
                rollout completes.
                {st.manifest_names.length ? (
                  <span className="mt-1 block text-xs opacity-90">
                    Manifests: {st.manifest_names.join(', ')}
                  </span>
                ) : null}
              </div>
            ) : null}
            {st.is_first_production_deploy && !st.manifest_warning ? (
              <Badge
                variant="outline"
                className="border-amber-500 text-amber-700"
              >
                First production deploy
              </Badge>
            ) : null}
            <p className="text-sm text-muted-foreground">{st.summary}</p>
            {st.deployment_status === 'sharding' && st.shard_percent != null ? (
              <div className="space-y-1">
                <div className="flex justify-between text-xs text-muted-foreground">
                  <span>
                    Day {st.current_day ?? '—'} of {st.rollout_days}
                  </span>
                  <span>{st.shard_percent}% fleet</span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-muted">
                  <div
                    className="h-full rounded-full bg-amber-500"
                    style={{ width: `${st.shard_percent}%` }}
                  />
                </div>
              </div>
            ) : null}
            {st.installable_condition ? (
              <p className="font-mono text-xs text-muted-foreground">
                {st.installable_condition}
              </p>
            ) : null}
            {showShardOverride ? (
              <div className="space-y-3 rounded-md border bg-muted/30 p-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <Switch
                      id={`shard-override-${pkgId}`}
                      checked={overrideEnabled}
                      disabled={busy}
                      onCheckedChange={(enabled) => {
                        setOverrideEnabled(enabled)
                        if (!enabled) {
                          overrideMut.mutate(null)
                        } else {
                          overrideMut.mutate(overrideValue)
                        }
                      }}
                    />
                    <Label
                      htmlFor={`shard-override-${pkgId}`}
                      className="font-normal"
                    >
                      Manual shard override
                    </Label>
                  </div>
                  <span className="font-mono text-sm tabular-nums">
                    {overrideEnabled
                      ? `${overrideValue}%`
                      : st.scheduled_shard_percent != null
                        ? `${st.scheduled_shard_percent}% (auto)`
                        : '—'}
                  </span>
                </div>
                {overrideEnabled ? (
                  <div className="space-y-2">
                    <Slider
                      min={1}
                      max={100}
                      step={1}
                      value={[overrideValue]}
                      disabled={busy}
                      onValueChange={(v) => setOverrideValue(v[0] ?? 1)}
                      onValueCommit={(v) => {
                        const pct = v[0] ?? 1
                        setOverrideValue(pct)
                        overrideMut.mutate(pct)
                      }}
                    />
                    <p className="text-xs text-muted-foreground">
                      Sets{' '}
                      <code className="text-xs">installable_condition</code> to{' '}
                      <code className="text-xs">
                        shard &lt;= {overrideValue}
                      </code>
                      . Automatic daily progression is paused while overridden.
                    </p>
                  </div>
                ) : (
                  <p className="text-xs text-muted-foreground">
                    Enable to pin a specific fleet percentage instead of the
                    scheduled daily rollout.
                  </p>
                )}
              </div>
            ) : null}
          </>
        ) : null}
      </CardContent>
    </Card>
  )
}
