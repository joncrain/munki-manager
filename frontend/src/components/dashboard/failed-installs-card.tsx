import { AlertTriangle } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Badge } from '@/components/ui/badge'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import type { FailedInstallSummary } from '@/lib/api'
import { formatRelativeTimeAgo } from '@/lib/format'

export function FailedInstallsCard({
  summary,
  isLoading,
}: {
  summary: FailedInstallSummary | undefined
  isLoading: boolean
}) {
  const items = summary?.items ?? []
  return (
    <Card className="flex h-full flex-col border-l-4 border-l-destructive/45 bg-destructive/4">
      <CardHeader className="flex flex-row items-start justify-between gap-3 space-y-0">
        <div>
          <CardTitle className="flex items-center gap-2 text-base">
            <AlertTriangle className="size-4 text-destructive" aria-hidden />
            Top install failures
          </CardTitle>
          <CardDescription>
            Software with failed install reports in the last{' '}
            {summary?.days ?? 7} days
          </CardDescription>
        </div>
        <Link
          to="/reporting/installs?status=failed"
          className="shrink-0 text-sm font-medium text-primary underline-offset-4 hover:underline"
        >
          View failures
        </Link>
      </CardHeader>
      <CardContent className="flex-1">
        {isLoading ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : !items.length ? (
          <p className="text-sm text-muted-foreground">
            No failed install reports in this window.
          </p>
        ) : (
          <ul className="space-y-2">
            {items.map((item) => (
              <li key={item.item_name}>
                <Link
                  to={`/reporting/installs?item_name=${encodeURIComponent(item.item_name)}`}
                  className="block rounded-md border bg-card/70 p-3 transition-colors hover:bg-muted/60"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">
                        {item.item_name}
                      </p>
                      <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">
                        {item.latest_error ||
                          item.latest_hostname ||
                          item.latest_serial_number ||
                          'Latest failure has no detail'}
                      </p>
                      {item.latest_at ? (
                        <p className="mt-1 text-xs text-muted-foreground">
                          Last failed {formatRelativeTimeAgo(item.latest_at)}
                        </p>
                      ) : null}
                    </div>
                    <div className="flex shrink-0 flex-col items-end gap-1">
                      <Badge variant="destructive">
                        {item.failure_count} failed
                      </Badge>
                      <span className="text-xs text-muted-foreground">
                        {item.machine_count} device
                        {item.machine_count === 1 ? '' : 's'}
                      </span>
                    </div>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}
