import { format, parseISO } from 'date-fns'
import { useId, useMemo } from 'react'
import { Area, AreaChart, CartesianGrid, XAxis, YAxis } from 'recharts'
import {
  type ChartConfig,
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
} from '@/components/ui/chart'
import type { CheckinHistoryPoint } from '@/lib/api'

const chartConfig = {
  installed: {
    label: 'Installed',
    color: 'var(--gruvbox-green)',
  },
  failed: {
    label: 'Failed',
    color: 'var(--gruvbox-red)',
  },
} satisfies ChartConfig

const SERIES_KEYS = ['installed', 'failed'] as const

type ChartRow = {
  date: string
  shortLabel: string
  installed: number
  failed: number
}

function mergeInstallSeries(
  installed: CheckinHistoryPoint[],
  failed: CheckinHistoryPoint[],
): ChartRow[] {
  const installedByDate = new Map(
    installed.map((point) => [point.date, point.count]),
  )
  const failedByDate = new Map(failed.map((point) => [point.date, point.count]))
  const dates = [
    ...new Set([
      ...installed.map((point) => point.date),
      ...failed.map((point) => point.date),
    ]),
  ].sort()

  return dates.map((date) => ({
    date,
    shortLabel: format(parseISO(date), 'MMM d'),
    installed: installedByDate.get(date) ?? 0,
    failed: failedByDate.get(date) ?? 0,
  }))
}

export function FleetInstallRowsChart({
  installedByDay,
  failedByDay,
}: {
  installedByDay: CheckinHistoryPoint[]
  failedByDay: CheckinHistoryPoint[]
}) {
  const chartId = useId().replace(/:/g, '')
  const chartData = useMemo(
    () => mergeInstallSeries(installedByDay, failedByDay),
    [installedByDay, failedByDay],
  )

  const hasActivity = useMemo(
    () => chartData.some((row) => row.installed > 0 || row.failed > 0),
    [chartData],
  )

  if (!hasActivity) {
    return (
      <p className="text-sm text-muted-foreground">
        No install report rows yet — they appear when clients send
        ManagedInstallReport data.
      </p>
    )
  }

  return (
    <ChartContainer
      config={chartConfig}
      className="aspect-auto h-[220px] w-full"
      initialDimension={{ width: 320, height: 220 }}
    >
      <AreaChart
        data={chartData}
        margin={{ top: 8, right: 8, left: 0, bottom: 0 }}
      >
        <defs>
          {SERIES_KEYS.map((key) => (
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
          ))}
        </defs>
        <CartesianGrid vertical={false} className="stroke-border/60" />
        <XAxis
          dataKey="shortLabel"
          tickLine={false}
          axisLine={false}
          tickMargin={8}
          minTickGap={16}
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
        {SERIES_KEYS.map((key) => (
          <Area
            key={key}
            dataKey={key}
            type="monotone"
            fill={`url(#fill-${chartId}-${key})`}
            stroke={`var(--color-${key})`}
            strokeWidth={2}
          />
        ))}
        <ChartLegend content={<ChartLegendContent />} />
      </AreaChart>
    </ChartContainer>
  )
}
