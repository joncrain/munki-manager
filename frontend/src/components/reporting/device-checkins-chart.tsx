import { useId } from 'react'
import { FleetTimeseriesChart } from '@/components/dashboard/fleet-timeseries-chart'
import type { CheckinHistoryPoint } from '@/lib/api'

export function DeviceCheckinsChart({
  history,
  total,
}: {
  history: CheckinHistoryPoint[] | undefined
  total: number | undefined
}) {
  const gradientId = useId().replace(/:/g, '')

  if (!total) {
    return (
      <p className="px-2 py-6 text-center text-sm text-muted-foreground">
        No check-in history yet. Data appears after the next client POST to{' '}
        <code className="rounded bg-muted px-1 py-0.5 text-xs">
          /reports/checkin
        </code>
        .
      </p>
    )
  }

  return (
    <FleetTimeseriesChart
      points={history ?? []}
      seriesLabel="Check-ins"
      gradientId={gradientId}
      strokeVar="var(--chart-1)"
      emptyMessage="No check-in activity in this period."
      height={200}
    />
  )
}
