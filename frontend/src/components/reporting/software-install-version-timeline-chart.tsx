import { format, parseISO } from 'date-fns'
import { useEffect, useId, useMemo, useState } from 'react'
import { Area, AreaChart, CartesianGrid, XAxis, YAxis } from 'recharts'
import {
  type ChartConfig,
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
} from '@/components/ui/chart'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { PkgInfoInstallReportSummary } from '@/lib/api'

const CHART_COLORS = [
  'var(--chart-1)',
  'var(--chart-2)',
  'var(--chart-3)',
  'var(--chart-4)',
  'var(--chart-5)',
] as const

const DAY_OPTIONS = [
  { value: '7', label: 'Last 7 days' },
  { value: '30', label: 'Last 30 days' },
  { value: '90', label: 'Last 90 days' },
] as const

function versionSeriesKey(index: number) {
  return `v${index}`
}

type ChartRow = {
  date: string
  shortLabel: string
  [seriesKey: string]: string | number
}

function buildChartRows(
  summary: PkgInfoInstallReportSummary,
  visibleVersions: Set<string>,
): ChartRow[] {
  const visible = summary.versions.filter((version) =>
    visibleVersions.has(version),
  )
  if (!visible.length) return []

  const dateSet = new Set<string>()
  for (const version of visible) {
    for (const point of summary.timeline_by_version[version] ?? []) {
      dateSet.add(point.date)
    }
  }

  const dates = [...dateSet].sort()
  return dates.map((date) => {
    const row: ChartRow = {
      date,
      shortLabel: format(parseISO(date), 'MMM d'),
    }
    for (const version of visible) {
      const index = summary.versions.indexOf(version)
      const key = versionSeriesKey(index)
      const point = summary.timeline_by_version[version]?.find(
        (p) => p.date === date,
      )
      row[key] = point?.count ?? 0
    }
    return row
  })
}

function buildChartConfig(
  summary: PkgInfoInstallReportSummary,
  visibleVersions: Set<string>,
): ChartConfig {
  const config: ChartConfig = {}
  for (const version of summary.versions) {
    if (!visibleVersions.has(version)) continue
    const index = summary.versions.indexOf(version)
    const key = versionSeriesKey(index)
    config[key] = {
      label: version,
      color: CHART_COLORS[index % CHART_COLORS.length],
    }
  }
  return config
}

export function SoftwareInstallVersionTimelineChart({
  summary,
  days,
  onDaysChange,
}: {
  summary: PkgInfoInstallReportSummary
  days: number
  onDaysChange: (days: number) => void
}) {
  const chartId = useId().replace(/:/g, '')
  const [visibleVersions, setVisibleVersions] = useState<Set<string>>(
    () => new Set(summary.versions),
  )

  useEffect(() => {
    setVisibleVersions(new Set(summary.versions))
  }, [summary.versions])

  const windowTotal = useMemo(
    () => summary.timeline.reduce((sum, point) => sum + point.count, 0),
    [summary.timeline],
  )

  const chartData = useMemo(
    () => buildChartRows(summary, visibleVersions),
    [summary, visibleVersions],
  )

  const chartConfig = useMemo(
    () => buildChartConfig(summary, visibleVersions),
    [summary, visibleVersions],
  )

  const visibleSeries = useMemo(
    () =>
      summary.versions
        .map((version, index) => ({ version, index }))
        .filter(({ version }) => visibleVersions.has(version)),
    [summary.versions, visibleVersions],
  )

  const toggleVersion = (version: string, checked: boolean) => {
    setVisibleVersions((current) => {
      const next = new Set(current)
      if (checked) {
        next.add(version)
      } else if (next.size > 1) {
        next.delete(version)
      }
      return next
    })
  }

  if (!summary.total_reports) {
    return (
      <p className="px-2 py-6 text-center text-sm text-muted-foreground">
        No install reports for this item yet. Rows appear when clients POST{' '}
        <code className="rounded bg-muted px-1 py-0.5 text-xs">
          install_results
        </code>{' '}
        on check-in.
      </p>
    )
  }

  if (windowTotal === 0) {
    return (
      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center justify-end gap-2">
          <Select
            value={String(days)}
            onValueChange={(value) => onDaysChange(Number(value))}
          >
            <SelectTrigger className="w-[160px]" aria-label="Activity range">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {DAY_OPTIONS.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <p className="px-2 py-6 text-center text-sm text-muted-foreground">
          {summary.total_reports} report
          {summary.total_reports === 1 ? '' : 's'} on file, but none in the last{' '}
          {days} days (by install or report time). Older activity is omitted
          from this chart.
        </p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          {summary.versions.map((version, index) => {
            const checked = visibleVersions.has(version)
            const color = CHART_COLORS[index % CHART_COLORS.length]
            const checkboxId = `${chartId}-version-${index}`
            return (
              <div key={version} className="flex items-center gap-2">
                <Checkbox
                  id={checkboxId}
                  checked={checked}
                  onCheckedChange={(value) =>
                    toggleVersion(version, value === true)
                  }
                />
                <Label
                  htmlFor={checkboxId}
                  className="flex items-center gap-2 text-sm font-normal"
                >
                  <span
                    className="size-2 shrink-0 rounded-[2px]"
                    style={{ backgroundColor: color }}
                    aria-hidden
                  />
                  {version}
                </Label>
              </div>
            )
          })}
        </div>
        <Select
          value={String(days)}
          onValueChange={(value) => onDaysChange(Number(value))}
        >
          <SelectTrigger className="w-[160px]" aria-label="Activity range">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {DAY_OPTIONS.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <ChartContainer
        config={chartConfig}
        className="aspect-auto h-[250px] w-full"
        initialDimension={{ width: 320, height: 250 }}
      >
        <AreaChart
          data={chartData}
          margin={{ top: 8, right: 8, left: 0, bottom: 0 }}
        >
          <defs>
            {visibleSeries.map(({ index }) => {
              const key = versionSeriesKey(index)
              return (
                <linearGradient
                  key={key}
                  id={`fill-${chartId}-${key}`}
                  x1="0"
                  y1="0"
                  x2="0"
                  y2="1"
                >
                  <stop
                    offset="5%"
                    stopColor={`var(--color-${key})`}
                    stopOpacity={0.35}
                  />
                  <stop
                    offset="95%"
                    stopColor={`var(--color-${key})`}
                    stopOpacity={0.02}
                  />
                </linearGradient>
              )
            })}
          </defs>
          <CartesianGrid vertical={false} />
          <XAxis
            dataKey="shortLabel"
            tickLine={false}
            axisLine={false}
            tickMargin={8}
            minTickGap={24}
          />
          <YAxis
            tickLine={false}
            axisLine={false}
            width={28}
            allowDecimals={false}
            domain={[0, 'auto']}
          />
          <ChartTooltip
            cursor={false}
            content={
              <ChartTooltipContent
                labelFormatter={(_, payload) => {
                  const row = payload?.[0]?.payload as
                    | { date?: string }
                    | undefined
                  return row?.date
                    ? format(parseISO(row.date), 'MMM d, yyyy')
                    : ''
                }}
                indicator="dot"
              />
            }
          />
          {visibleSeries.map(({ index }) => {
            const key = versionSeriesKey(index)
            return (
              <Area
                key={key}
                dataKey={key}
                type="monotone"
                fill={`url(#fill-${chartId}-${key})`}
                stroke={`var(--color-${key})`}
                strokeWidth={2}
              />
            )
          })}
          <ChartLegend content={<ChartLegendContent />} />
        </AreaChart>
      </ChartContainer>
    </div>
  )
}
