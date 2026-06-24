import { MoonStar } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Badge } from '@/components/ui/badge'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import type { StaleMachinePreview } from '@/lib/api'
import { formatRelativeTimeAgo } from '@/lib/format'

export function StaleMachinesCard({
  preview,
  isLoading,
}: {
  preview: StaleMachinePreview | undefined
  isLoading: boolean
}) {
  const items = preview?.items ?? []
  return (
    <Card className="flex h-full flex-col border-l-4 border-l-gruvbox-orange/50 bg-gruvbox-orange/6">
      <CardHeader className="flex flex-row items-start justify-between gap-3 space-y-0">
        <div>
          <CardTitle className="flex items-center gap-2 text-base">
            <MoonStar className="size-4 text-gruvbox-orange" aria-hidden />
            Stale devices
          </CardTitle>
          <CardDescription>
            Machines with no check-in for {preview?.days ?? 30}+ days
          </CardDescription>
        </div>
        <Link
          to="/reporting?stale=30"
          className="shrink-0 text-sm font-medium text-primary underline-offset-4 hover:underline"
        >
          View devices
        </Link>
      </CardHeader>
      <CardContent className="flex-1">
        {isLoading ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : !items.length ? (
          <p className="text-sm text-muted-foreground">
            No stale devices in this window.
          </p>
        ) : (
          <ul className="space-y-2">
            {items.map((item) => (
              <li key={item.id}>
                <Link
                  to={`/reporting/devices/${item.id}`}
                  className="block rounded-md border bg-card/70 p-3 transition-colors hover:bg-muted/60"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">
                        {item.hostname || item.serial_number}
                      </p>
                      <p className="truncate text-xs text-muted-foreground">
                        {item.manifest_name || 'No manifest'}
                      </p>
                    </div>
                    <div className="shrink-0 text-right">
                      <Badge variant="secondary">
                        {item.last_checkin_at
                          ? formatRelativeTimeAgo(item.last_checkin_at)
                          : 'Never'}
                      </Badge>
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
