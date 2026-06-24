import { History } from 'lucide-react'
import { Link } from 'react-router-dom'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import type { AuditLogRead } from '@/lib/api'
import { formatRelativeTimeAgo } from '@/lib/format'

function humanize(value: string) {
  return value.replace(/_/g, ' ')
}

export function RecentActivityCard({
  logs,
  isLoading,
}: {
  logs: AuditLogRead[]
  isLoading: boolean
}) {
  return (
    <Card className="flex h-full flex-col">
      <CardHeader className="flex flex-row items-start justify-between gap-3 space-y-0">
        <div>
          <CardTitle className="flex items-center gap-2 text-base">
            <History className="size-4 text-muted-foreground" aria-hidden />
            Recent activity
          </CardTitle>
          <CardDescription>Latest admin and automation changes</CardDescription>
        </div>
        <Link
          to="/audit"
          className="shrink-0 text-sm font-medium text-primary underline-offset-4 hover:underline"
        >
          View audit
        </Link>
      </CardHeader>
      <CardContent className="flex-1">
        {isLoading ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : !logs.length ? (
          <p className="text-sm text-muted-foreground">
            No recent audit entries.
          </p>
        ) : (
          <ul className="space-y-2">
            {logs.map((log) => (
              <li key={log.id} className="rounded-md border bg-card/70 p-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">
                      {humanize(log.action)} {humanize(log.entity_type)}
                    </p>
                    <p className="truncate text-xs text-muted-foreground">
                      {log.entity_name || log.entity_id}
                    </p>
                  </div>
                  <span className="shrink-0 text-xs text-muted-foreground">
                    {formatRelativeTimeAgo(log.created_at)}
                  </span>
                </div>
                {log.user_email ? (
                  <p className="mt-1 truncate text-xs text-muted-foreground">
                    {log.user_email}
                  </p>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}
