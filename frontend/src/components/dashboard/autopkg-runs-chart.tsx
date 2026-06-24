import {
  eachDayOfInterval,
  format,
  parseISO,
  startOfDay,
  subDays,
} from 'date-fns'
import { useId, useMemo } from 'react'
import { FleetTimeseriesChart } from '@/components/dashboard/fleet-timeseries-chart'
import type { AutoPkgRunRead } from '@/lib/api'

const DAYS = 30

function buildSeries(runs: AutoPkgRunRead[]) {
  const end = startOfDay(new Date())
  const start = subDays(end, DAYS - 1)
  const keys = eachDayOfInterval({ start, end }).map((d) =>
    format(d, 'yyyy-MM-dd'),
  )
  const counts = new Map<string, number>()
  for (const k of keys) counts.set(k, 0)
  for (const run of runs) {
    const k = format(parseISO(run.created_at), 'yyyy-MM-dd')
    if (counts.has(k)) counts.set(k, (counts.get(k) ?? 0) + 1)
  }
  return keys.map((date) => ({
    date,
    count: counts.get(date) ?? 0,
  }))
}

export function AutoPkgRunsChart({ runs }: { runs: AutoPkgRunRead[] }) {
  const gradientId = useId().replace(/:/g, '')
  const points = useMemo(() => buildSeries(runs), [runs])

  return (
    <FleetTimeseriesChart
      points={points}
      seriesLabel="Runs"
      gradientId={gradientId}
      strokeVar="var(--chart-2)"
      emptyMessage="No AutoPkg runs yet — activity will appear here after the first run."
    />
  )
}
