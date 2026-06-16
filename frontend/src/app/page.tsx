import { useQuery } from '@tanstack/react-query'
import {
  Activity,
  BookMarked,
  CheckCircle,
  FileText,
  FolderOpen,
  LayoutDashboard,
  MonitorSmartphone,
  MoonStar,
  Package,
  Percent,
  Play,
  ScrollText,
  ShieldAlert,
  Timer,
} from 'lucide-react'
import type { ComponentType, ReactNode } from 'react'
import { useId } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '@/components/auth-provider'
import { AutoPkgRunsChart } from '@/components/dashboard/autopkg-runs-chart'
import { FleetTimeseriesChart } from '@/components/dashboard/fleet-timeseries-chart'
import { PageHeading } from '@/components/page-heading'
import {
  CatalogSoftwareAvatarCircles,
  SoftwareAvatarCircles,
  SoftwareNameAvatarCircles,
  useSoftwarePreviewPackages,
} from '@/components/software-avatar-circles'
import { SoftwareIcon } from '@/components/software-icon'
import { Badge } from '@/components/ui/badge'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { useDocumentTitle } from '@/hooks/use-document-title'
import {
  type AutoPkgRecipeRead,
  type AutoPkgRunRead,
  api,
  type CatalogRead,
  type FleetActivityTimeseries,
  type FleetComplianceOverview,
  type ManifestRead,
  type PaginatedResponse,
  type PkgInfoPromotionQueueItemRead,
  type RecipeTrustSummaryResponse,
  type TrustPendingCountResponse,
} from '@/lib/api'
import { formatDate } from '@/lib/format'
import { parseManifestItemRef } from '@/lib/manifest-item-ref'
import { manifestTitle } from '@/lib/manifest-title'
import {
  type MunkiAccentKey,
  munkiAccents,
  munkiSectionHeadingClass,
  munkiSectionMarkerClass,
} from '@/lib/munki-accents'
import { PAGE_KEYS } from '@/lib/page-keys'
import { cn } from '@/lib/utils'

const DASHBOARD_MANIFEST_LIST_AVATAR_MAX = 6

/** Pkg name roots for SoftwareNameAvatarCircles, matching manifest cards (managed → optional → uninstall). */
function namesForManifestDashboardIcons(m: ManifestRead): string[] {
  const from = (refs: string[]) =>
    refs.map((r) => parseManifestItemRef(r).baseName)
  if (m.managed_installs.length) {
    return from(m.managed_installs)
  }
  if (m.optional_installs.length) {
    return from(m.optional_installs)
  }
  if (m.managed_uninstalls.length) {
    return from(m.managed_uninstalls)
  }
  return []
}

type StatLinkCardProps = {
  href: string
  title: string
  icon: ComponentType<{ className?: string; 'aria-hidden'?: boolean }>
  children: ReactNode
  footer: ReactNode
} & (
  | { accent: MunkiAccentKey; borderClass?: never; iconClass?: never }
  | { accent?: never; borderClass: string; iconClass: string }
)

function StatLinkCard({
  href,
  title,
  icon: Icon,
  children,
  footer,
  accent,
  borderClass,
  iconClass,
}: StatLinkCardProps) {
  const titleId = useId()
  const cardClass =
    accent !== undefined
      ? munkiAccents[accent].statCard
      : cn('border-l-4', borderClass, 'bg-muted/40')
  const iconCls = accent !== undefined ? munkiAccents[accent].icon : iconClass
  return (
    <div className="relative rounded-xl outline-none ring-offset-background transition-opacity hover:opacity-95 focus-within:ring-2 focus-within:ring-ring focus-within:ring-offset-2">
      <Link
        to={href}
        className="absolute inset-0 z-1 rounded-xl"
        aria-labelledby={titleId}
      />
      <Card
        className={cn('relative z-2 h-full pointer-events-none', cardClass)}
      >
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle id={titleId} className="text-sm font-medium">
            {title}
          </CardTitle>
          <Icon className={cn('h-4 w-4', iconCls)} aria-hidden />
        </CardHeader>
        <CardContent className="space-y-1">
          {children}
          <p className="text-xs text-muted-foreground [&_a]:pointer-events-auto [&_a]:relative [&_a]:z-3">
            {footer}
          </p>
        </CardContent>
      </Card>
    </div>
  )
}

export default function DashboardPage() {
  const { canRead, loading: authLoading } = useAuth()
  const canSeeSoftware = !authLoading && canRead(PAGE_KEYS.munkiSoftware)
  const canSeeRecipes = !authLoading && canRead(PAGE_KEYS.autopkgRecipes)
  const canSeeApprovals = !authLoading && canRead(PAGE_KEYS.autopkgApprovals)

  useDocumentTitle('Overview', 'Dashboard')

  const { data: pendingTrustDash } = useQuery({
    queryKey: ['pending-trust-changes-count'],
    queryFn: () =>
      api.get<TrustPendingCountResponse>(
        '/autopkg/trust-changes/pending-count',
      ),
    enabled: canSeeApprovals,
    staleTime: 30_000,
  })

  const { data: trustSummary } = useQuery({
    queryKey: ['autopkg-recipes', 'trust-summary'],
    queryFn: () =>
      api.get<RecipeTrustSummaryResponse>('/autopkg/recipes/trust-summary'),
    enabled: canSeeRecipes,
    staleTime: 30_000,
  })

  const { data: catalogs } = useQuery({
    queryKey: ['catalogs'],
    queryFn: () => api.get<CatalogRead[]>('/catalogs'),
  })

  const { data: runsPage } = useQuery({
    queryKey: ['autopkg-runs-dash'],
    queryFn: () =>
      api.get<PaginatedResponse<AutoPkgRunRead>>('/autopkg/runs?page_size=100'),
  })

  const { data: softwarePreviewPage } = useSoftwarePreviewPackages({
    pageSize: 6,
  })

  const { data: promotionQueue, isLoading: promotionQueueLoading } = useQuery({
    queryKey: ['pkginfo', 'promotion-queue'],
    queryFn: () =>
      api.get<PkgInfoPromotionQueueItemRead[]>(
        '/pkginfo/promotion-queue?limit=8',
      ),
    enabled: canSeeSoftware,
    staleTime: 30_000,
  })

  const { data: manifests } = useQuery({
    queryKey: ['manifests'],
    queryFn: () => api.get<ManifestRead[]>('/manifests'),
  })

  const { data: recipesDash } = useQuery({
    queryKey: ['autopkg-recipes-dash'],
    queryFn: () =>
      api.get<PaginatedResponse<AutoPkgRecipeRead>>(
        '/autopkg/recipes?page_size=1&page=1',
      ),
  })

  const { data: approvals } = useQuery({
    queryKey: ['pending-approvals'],
    queryFn: () => api.get<unknown[]>('/autopkg/approvals'),
  })

  const { data: compliance, isLoading: complianceLoading } = useQuery({
    queryKey: ['reports-compliance'],
    queryFn: () => api.get<FleetComplianceOverview>('/reports/compliance'),
  })

  const { data: fleetActivity, isLoading: fleetActivityLoading } = useQuery({
    queryKey: ['reports-fleet-activity', 30],
    queryFn: () =>
      api.get<FleetActivityTimeseries>('/reports/fleet-activity?days=30'),
  })

  const runs = runsPage?.items ?? []
  const totalTitles = softwarePreviewPage?.total ?? 0
  const softwarePreviewItems = softwarePreviewPage?.items ?? []
  const totalCatalogs = catalogs?.length ?? 0
  const totalManifests = manifests?.length ?? 0
  const totalRecipes = recipesDash?.total ?? 0
  const totalRuns = runsPage?.total ?? 0
  const lastRun = runs[0]
  const pendingApprovals = Array.isArray(approvals) ? approvals.length : 0
  const pendingTrustQueueCount = pendingTrustDash?.count ?? 0

  return (
    <div className="space-y-10">
      <PageHeading
        icon={LayoutDashboard}
        accent="dashboard"
        title="Dashboard"
      />

      <section className="space-y-4">
        <h2 className={munkiSectionHeadingClass()}>
          <span className={munkiSectionMarkerClass()} aria-hidden />
          Munki
        </h2>
        <div className="grid gap-4 md:grid-cols-3">
          <Card
            className={cn(
              'flex h-full flex-col',
              munkiAccents.software.statCard,
            )}
          >
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">
                <Link
                  to="/software"
                  className="text-foreground hover:underline"
                >
                  Software
                </Link>
              </CardTitle>
              <Link
                to="/software"
                className="text-foreground"
                aria-label="Open software"
              >
                <Package
                  className={cn('h-4 w-4', munkiAccents.software.icon)}
                  aria-hidden
                />
              </Link>
            </CardHeader>
            <CardContent className="flex flex-1 flex-col space-y-1">
              <div className="flex min-h-10 items-center justify-between gap-3">
                <div
                  className="text-2xl font-bold"
                  style={{ fontVariantNumeric: 'tabular-nums' }}
                >
                  {totalTitles}
                </div>
                <SoftwareAvatarCircles
                  packages={softwarePreviewItems}
                  total={totalTitles}
                  interactive={false}
                />
              </div>
              <p className="text-xs text-muted-foreground">
                Packages in the repository
              </p>
              {canSeeSoftware ? (
                <div className="mt-3 space-y-3 border-t border-border/60 pt-3">
                  <div>
                    <h3 className="flex items-center gap-2 text-sm font-semibold text-foreground">
                      <Timer
                        className="h-4 w-4 shrink-0 text-muted-foreground"
                        aria-hidden
                      />
                      Auto-promotion
                    </h3>
                    <p className="pt-0.5 text-xs text-muted-foreground">
                      Channel path: dwell in progress, or next move on the next
                      promotion run
                    </p>
                  </div>
                  {promotionQueueLoading ? (
                    <p
                      className="text-sm text-muted-foreground"
                      aria-live="polite"
                    >
                      Loading…
                    </p>
                  ) : !promotionQueue?.length ? (
                    <p className="text-sm text-muted-foreground">
                      No versions are in an active channel step (source catalog)
                      right now.
                    </p>
                  ) : (
                    <section
                      className="max-h-72 min-h-0 overflow-y-auto overscroll-y-contain pr-0.5"
                      aria-label="Auto-promotion queue"
                    >
                      <ul className="space-y-2">
                        {promotionQueue.map((row) => {
                          const title = row.display_name || row.name
                          return (
                            <li key={row.id}>
                              <Link
                                to={`/software/${row.id}`}
                                className={cn(
                                  'flex flex-col gap-0.5 rounded-md border p-2.5 text-sm transition-colors sm:flex-row sm:items-center sm:justify-between',
                                  munkiAccents.software.overviewRow,
                                )}
                              >
                                <div className="flex min-w-0 items-start gap-3 sm:items-center">
                                  <SoftwareIcon
                                    className="mt-0.5 sm:mt-0"
                                    name={row.name}
                                    displayName={row.display_name}
                                    size="sm"
                                  />
                                  <div className="min-w-0">
                                    <div className="truncate font-medium">
                                      {title}
                                    </div>
                                    <div className="truncate text-xs text-muted-foreground">
                                      <span className="font-medium text-foreground/80">
                                        {row.channel_name}
                                      </span>
                                      <span> · </span>
                                      {row.next_source_catalog} →{' '}
                                      {row.next_target_catalog}
                                    </div>
                                  </div>
                                </div>
                                <div className="shrink-0 pl-11 text-xs sm:pl-0 sm:text-right">
                                  {row.leg_status === 'waiting' ? (
                                    <span className="text-muted-foreground">
                                      ~{row.days_remaining}d ·{' '}
                                      {formatDate(row.promote_at)}
                                    </span>
                                  ) : (
                                    <span className="text-muted-foreground">
                                      Eligible next run
                                    </span>
                                  )}
                                </div>
                              </Link>
                            </li>
                          )
                        })}
                      </ul>
                    </section>
                  )}
                </div>
              ) : null}
            </CardContent>
          </Card>

          <Card
            className={cn(
              'flex h-full flex-col',
              munkiAccents.catalogs.statCard,
            )}
          >
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">
                <Link
                  to="/catalogs"
                  className="text-foreground hover:underline"
                >
                  Catalogs
                </Link>
              </CardTitle>
              <Link
                to="/catalogs"
                className="text-foreground"
                aria-label="Open catalogs"
              >
                <FolderOpen
                  className={cn('h-4 w-4', munkiAccents.catalogs.icon)}
                  aria-hidden
                />
              </Link>
            </CardHeader>
            <CardContent className="flex flex-1 flex-col space-y-3">
              <div
                className="text-2xl font-bold"
                style={{ fontVariantNumeric: 'tabular-nums' }}
              >
                {totalCatalogs}
              </div>
              <p className="text-xs text-muted-foreground">
                Production and staging catalogs with item counts
              </p>
              {catalogs?.length ? (
                <div className="space-y-3">
                  {catalogs.map((cat) => (
                    <Link
                      key={cat.id}
                      to="/catalogs"
                      className={cn(
                        'flex items-center justify-between gap-2 rounded-md border p-3 transition-colors sm:gap-3',
                        munkiAccents.catalogs.overviewRow,
                      )}
                    >
                      <div className="flex min-w-0 flex-1 items-center gap-2">
                        <span className="truncate font-medium">{cat.name}</span>
                        {cat.is_production && (
                          <Badge variant="default">Production</Badge>
                        )}
                      </div>
                      <div className="flex shrink-0 items-center gap-2">
                        <span
                          className="whitespace-nowrap text-sm text-muted-foreground"
                          style={{ fontVariantNumeric: 'tabular-nums' }}
                        >
                          {cat.item_count} items
                        </span>
                        <CatalogSoftwareAvatarCircles
                          catalogName={cat.name}
                          className="shrink-0"
                          interactive={false}
                          itemCount={cat.item_count}
                        />
                      </div>
                    </Link>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">No catalogs yet</p>
              )}
            </CardContent>
          </Card>

          <Card
            className={cn(
              'flex h-full flex-col',
              munkiAccents.manifests.statCard,
            )}
          >
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">
                <Link
                  to="/manifests"
                  className="text-foreground hover:underline"
                >
                  Manifests
                </Link>
              </CardTitle>
              <Link
                to="/manifests"
                className="text-foreground"
                aria-label="Open manifests"
              >
                <ScrollText
                  className={cn('h-4 w-4', munkiAccents.manifests.icon)}
                  aria-hidden
                />
              </Link>
            </CardHeader>
            <CardContent className="flex flex-1 flex-col space-y-3">
              <div
                className="text-2xl font-bold"
                style={{ fontVariantNumeric: 'tabular-nums' }}
              >
                {totalManifests}
              </div>
              <p className="text-xs text-muted-foreground">
                Computer manifests and install rules
              </p>
              {manifests?.length ? (
                <div className="space-y-3">
                  {[...manifests]
                    .sort((a, b) => a.name.localeCompare(b.name))
                    .map((m) => {
                      const installCount =
                        m.managed_installs.length +
                        m.managed_uninstalls.length +
                        m.optional_installs.length
                      const iconNames = namesForManifestDashboardIcons(m)
                      return (
                        <Link
                          key={m.id}
                          to={`/manifests/${m.id}`}
                          className={cn(
                            'flex items-center justify-between gap-2 rounded-md border p-3 transition-colors sm:gap-3',
                            munkiAccents.manifests.overviewRow,
                          )}
                        >
                          <div className="flex min-w-0 flex-1 items-start gap-2 sm:items-center sm:gap-3">
                            <FileText
                              className={cn(
                                'mt-0.5 h-5 w-5 shrink-0 sm:mt-0',
                                munkiAccents.manifests.icon,
                              )}
                              aria-hidden
                            />
                            <div className="min-w-0 flex-1">
                              <div className="truncate font-medium">
                                {manifestTitle(m)}
                              </div>
                              {manifestTitle(m) !== m.name ? (
                                <div className="truncate text-xs text-muted-foreground">
                                  {m.name}
                                </div>
                              ) : null}
                            </div>
                          </div>
                          <div className="flex shrink-0 items-center gap-2">
                            <SoftwareNameAvatarCircles
                              className="shrink-0"
                              hideWhenEmpty
                              interactive={false}
                              maxVisible={DASHBOARD_MANIFEST_LIST_AVATAR_MAX}
                              names={iconNames}
                            />
                            <span
                              className="whitespace-nowrap text-sm text-muted-foreground"
                              style={{ fontVariantNumeric: 'tabular-nums' }}
                            >
                              {installCount} installs
                            </span>
                          </div>
                        </Link>
                      )
                    })}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">
                  No manifests yet
                </p>
              )}
            </CardContent>
          </Card>
        </div>
      </section>

      <section className="space-y-4">
        <h2 className={munkiSectionHeadingClass()}>
          <span className={munkiSectionMarkerClass()} aria-hidden />
          Device reporting
        </h2>
        <p className="max-w-2xl text-sm text-muted-foreground">
          Macs checking in via the Munki Manager agent or Munki postflight. Open{' '}
          <Link
            to="/reporting"
            className="font-medium text-primary underline-offset-4 hover:underline"
          >
            Devices
          </Link>{' '}
          or{' '}
          <Link
            to="/reporting/installs"
            className="font-medium text-primary underline-offset-4 hover:underline"
          >
            Installs
          </Link>{' '}
          for full lists.
        </p>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Card
            className={cn(
              'border-l-4 border-l-gruvbox-blue/50 bg-gruvbox-blue/[0.06]',
            )}
          >
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Fleet size</CardTitle>
              <MonitorSmartphone
                className="size-4 text-gruvbox-blue"
                aria-hidden
              />
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-semibold">
                {complianceLoading ? '—' : (compliance?.total_machines ?? 0)}
              </p>
              <CardDescription>machines in database</CardDescription>
            </CardContent>
          </Card>
          <Card
            className={cn(
              'border-l-4 border-l-gruvbox-green/50 bg-gruvbox-green/[0.06]',
            )}
          >
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Active (7d)</CardTitle>
              <Activity className="size-4 text-gruvbox-green" aria-hidden />
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-semibold">
                {complianceLoading
                  ? '—'
                  : (compliance?.checked_in_last_7_days ?? 0)}
              </p>
              <CardDescription>checked in recently</CardDescription>
            </CardContent>
          </Card>
          <Card
            className={cn(
              'border-l-4 border-l-gruvbox-orange/50 bg-gruvbox-orange/[0.07]',
            )}
          >
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">
                Stale (30d+)
              </CardTitle>
              <MoonStar className="size-4 text-gruvbox-orange" aria-hidden />
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-semibold">
                {complianceLoading
                  ? '—'
                  : (compliance?.stale_over_30_days ?? 0)}
              </p>
              <CardDescription>no check-in in 30 days</CardDescription>
            </CardContent>
          </Card>
          <Card
            className={cn(
              'border-l-4 border-l-gruvbox-purple/50 bg-gruvbox-purple/[0.06]',
            )}
          >
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">7-day reach</CardTitle>
              <Percent className="size-4 text-gruvbox-purple" aria-hidden />
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-semibold">
                {complianceLoading
                  ? '—'
                  : `${compliance?.compliance_percentage ?? 0}%`}
              </p>
              <CardDescription>of fleet reporting weekly</CardDescription>
            </CardContent>
          </Card>
        </div>

        <div className="grid gap-4 lg:grid-cols-2">
          <Card
            className={cn('flex flex-col', munkiAccents.reporting.statCard)}
          >
            <CardHeader className="flex flex-row items-start justify-between gap-2 space-y-0">
              <div>
                <CardTitle>Check-ins over time</CardTitle>
                <CardDescription>
                  Check-in events per day (last 30 days)
                </CardDescription>
              </div>
              <Link
                to="/reporting"
                className="shrink-0 text-sm font-medium text-primary underline-offset-4 hover:underline"
              >
                Devices
              </Link>
            </CardHeader>
            <CardContent className="flex-1">
              {fleetActivityLoading ? (
                <p className="text-sm text-muted-foreground">Loading…</p>
              ) : (
                <FleetTimeseriesChart
                  points={fleetActivity?.checkins_by_day ?? []}
                  seriesLabel="Check-ins"
                  gradientId="fillFleetCheckins"
                  strokeVar="var(--chart-1)"
                  emptyMessage="No check-ins yet — data appears after Macs report in."
                />
              )}
            </CardContent>
          </Card>

          <Card
            className={cn('flex flex-col', munkiAccents.reporting.statCard)}
          >
            <CardHeader className="flex flex-row items-start justify-between gap-2 space-y-0">
              <div>
                <CardTitle>Install rows over time</CardTitle>
                <CardDescription>
                  Managed install report rows recorded per day (last 30 days)
                </CardDescription>
              </div>
              <Link
                to="/reporting/installs"
                className="shrink-0 text-sm font-medium text-primary underline-offset-4 hover:underline"
              >
                Installs
              </Link>
            </CardHeader>
            <CardContent className="flex-1">
              {fleetActivityLoading ? (
                <p className="text-sm text-muted-foreground">Loading…</p>
              ) : (
                <FleetTimeseriesChart
                  points={fleetActivity?.install_rows_by_day ?? []}
                  seriesLabel="Rows"
                  gradientId="fillFleetInstalls"
                  strokeVar="var(--chart-3)"
                  emptyMessage="No install report rows yet — they appear when clients send ManagedInstallReport data."
                />
              )}
            </CardContent>
          </Card>
        </div>
      </section>

      <section className="space-y-4">
        <h2 className="text-xl font-semibold tracking-tight">AutoPkg</h2>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <StatLinkCard
            href="/approvals"
            borderClass="border-l-gruvbox-yellow/50"
            title="Import Approvals"
            icon={CheckCircle}
            iconClass="text-gruvbox-yellow"
            footer="Import pipeline results awaiting review"
          >
            <div
              className="text-2xl font-bold"
              style={{ fontVariantNumeric: 'tabular-nums' }}
            >
              {pendingApprovals}
            </div>
          </StatLinkCard>

          <StatLinkCard
            href="/approvals"
            borderClass="border-l-amber-500/50"
            title="Trust approvals"
            icon={ShieldAlert}
            iconClass="text-amber-500"
            footer="Parent recipe trust changes to review"
          >
            <div
              className="text-2xl font-bold"
              style={{ fontVariantNumeric: 'tabular-nums' }}
            >
              {canSeeApprovals ? pendingTrustQueueCount : '—'}
            </div>
          </StatLinkCard>

          <StatLinkCard
            href="/autopkg/runs"
            borderClass="border-l-gruvbox-red/50"
            title="Runs"
            icon={Play}
            iconClass="text-gruvbox-red"
            footer="Total runs recorded in the system"
          >
            <div className="space-y-1">
              <div
                className="text-2xl font-bold"
                style={{ fontVariantNumeric: 'tabular-nums' }}
              >
                {totalRuns}
              </div>
              {lastRun ? (
                <div className="flex flex-wrap items-center gap-2">
                  <Badge
                    variant={
                      lastRun.status === 'completed'
                        ? 'default'
                        : lastRun.status === 'failed'
                          ? 'destructive'
                          : 'secondary'
                    }
                  >
                    {lastRun.status}
                  </Badge>
                  <span className="text-xs text-muted-foreground">
                    {lastRun.recipes_imported ?? 0} imported,{' '}
                    {lastRun.recipes_failed ?? 0} failed
                  </span>
                </div>
              ) : null}
            </div>
          </StatLinkCard>

          <StatLinkCard
            href="/autopkg/recipes"
            borderClass="border-l-gruvbox-orange/50"
            title="Recipes"
            icon={BookMarked}
            iconClass="text-gruvbox-orange"
            footer={
              !canSeeRecipes ? (
                'Configured AutoPkg recipe overrides'
              ) : trustSummary ? (
                <span className="inline-flex flex-wrap gap-x-2 gap-y-1">
                  <Link
                    to="/autopkg/recipes?trust=verified"
                    className="text-gruvbox-green hover:underline"
                  >
                    {trustSummary.verified} verified
                  </Link>
                  <span className="text-muted-foreground" aria-hidden>
                    ·
                  </span>
                  <Link
                    to="/autopkg/recipes?trust=failed"
                    className="text-destructive hover:underline"
                  >
                    {trustSummary.failed} failed
                  </Link>
                  <span className="text-muted-foreground" aria-hidden>
                    ·
                  </span>
                  <Link
                    to="/autopkg/recipes?trust=pending_approval"
                    className="text-amber-600 dark:text-amber-400 hover:underline"
                  >
                    {trustSummary.pending_approval} pending
                  </Link>
                  <span className="text-muted-foreground" aria-hidden>
                    ·
                  </span>
                  <Link
                    to="/autopkg/recipes?trust=unknown"
                    className="text-muted-foreground hover:underline"
                  >
                    {trustSummary.unknown} unknown
                  </Link>
                </span>
              ) : (
                'Loading trust breakdown…'
              )
            }
          >
            <div
              className="text-2xl font-bold"
              style={{ fontVariantNumeric: 'tabular-nums' }}
            >
              {totalRecipes}
            </div>
          </StatLinkCard>
        </div>

        <Card>
          <CardHeader className="flex flex-row items-start justify-between gap-2 space-y-0">
            <div>
              <CardTitle>Run activity</CardTitle>
              <CardDescription>
                Runs per day over the last 30 days (from your 100 most recent
                runs)
              </CardDescription>
            </div>
            <Link
              to="/autopkg/runs"
              className="text-sm font-medium text-primary underline-offset-4 hover:underline"
            >
              View all
            </Link>
          </CardHeader>
          <CardContent>
            <AutoPkgRunsChart runs={runs} />
          </CardContent>
        </Card>
      </section>
    </div>
  )
}
