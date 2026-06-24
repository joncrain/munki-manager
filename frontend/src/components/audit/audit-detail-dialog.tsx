import { JsonSnapshotDiff } from '@/components/json-snapshot-diff'
import { Badge } from '@/components/ui/badge'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import type { AuditLogRead } from '@/lib/api'
import { auditActionVariant, formatAuditJson } from '@/lib/audit-display'
import { formatDateTime } from '@/lib/format'
import { cn } from '@/lib/utils'

const auditDetailTabTrigger = (activeRing: string) =>
  cn(
    'rounded-md border border-transparent px-3 py-1.5 text-sm font-medium',
    'text-muted-foreground transition-[background-color,border-color,color,box-shadow]',
    'hover:bg-background/70 hover:text-foreground',
    'data-[state=active]:bg-background data-[state=active]:text-foreground data-[state=active]:shadow-sm',
    activeRing,
  )

function AuditJsonPanel({
  value,
  label,
  variant,
}: {
  value: unknown
  label: string
  variant: 'before' | 'after' | 'changes'
}) {
  const accent =
    variant === 'before'
      ? 'border-l-red-500/80 bg-red-500/8'
      : variant === 'after'
        ? 'border-l-emerald-500/80 bg-emerald-500/8'
        : 'border-l-amber-500/80 bg-amber-500/8'

  const headerTone =
    variant === 'before'
      ? 'text-red-800 dark:text-red-300'
      : variant === 'after'
        ? 'text-emerald-800 dark:text-emerald-300'
        : 'text-amber-800 dark:text-amber-300'

  return (
    <div className={cn('overflow-hidden rounded-md border border-l-4', accent)}>
      <div
        className={cn(
          'border-b bg-muted/50 px-3 py-2 text-xs font-semibold tracking-wide uppercase',
          headerTone,
        )}
      >
        {label}
      </div>
      <ScrollArea className="h-[min(50vh,360px)] overscroll-contain bg-muted/20">
        <pre
          className="m-0 min-w-min p-4 text-sm leading-relaxed font-mono whitespace-pre"
          translate="no"
        >
          {formatAuditJson(value)}
        </pre>
      </ScrollArea>
    </div>
  )
}

export function AuditDetailDialog({
  entry,
  open,
  onOpenChange,
}: {
  entry: AuditLogRead | null
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  if (!entry) return null

  const hasBefore = entry.before_snapshot != null
  const hasAfter = entry.after_snapshot != null
  const hasChanges = entry.changes != null
  const hasDiff = hasBefore && hasAfter
  const defaultTab = hasDiff
    ? 'diff'
    : hasChanges
      ? 'changes'
      : hasAfter
        ? 'after'
        : 'before'

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[min(90vh,720px)] flex-col gap-4 overscroll-contain sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle className="flex flex-wrap items-center gap-2 text-pretty">
            <Badge variant={auditActionVariant(entry.action)}>
              {entry.action}
            </Badge>
            <span className="text-base font-medium">
              {entry.user_email || 'system'}
            </span>
          </DialogTitle>
          <DialogDescription asChild>
            <div className="space-y-1 text-sm text-muted-foreground">
              <p suppressHydrationWarning>{formatDateTime(entry.created_at)}</p>
              {entry.entity_type ? (
                <p>
                  {entry.entity_type}
                  {entry.entity_name || entry.entity_id
                    ? ` · ${entry.entity_name || entry.entity_id}`
                    : ''}
                </p>
              ) : null}
              {entry.ip_address ? <p>IP: {entry.ip_address}</p> : null}
              {entry.notes ? (
                <p className="text-foreground">{entry.notes}</p>
              ) : null}
            </div>
          </DialogDescription>
        </DialogHeader>

        {hasDiff || hasChanges || hasBefore || hasAfter ? (
          <Tabs
            defaultValue={defaultTab}
            className="flex min-h-0 flex-1 flex-col gap-3"
          >
            <TabsList className="h-auto w-full flex-wrap justify-start gap-1 rounded-lg border bg-muted/40 p-1">
              {hasDiff ? (
                <TabsTrigger
                  value="diff"
                  className={auditDetailTabTrigger(
                    'data-[state=active]:border-sky-500/40 data-[state=active]:ring-2 data-[state=active]:ring-sky-500/25',
                  )}
                >
                  Diff
                </TabsTrigger>
              ) : null}
              {hasChanges ? (
                <TabsTrigger
                  value="changes"
                  className={auditDetailTabTrigger(
                    'data-[state=active]:border-amber-500/40 data-[state=active]:ring-2 data-[state=active]:ring-amber-500/25',
                  )}
                >
                  Changes
                </TabsTrigger>
              ) : null}
              {hasBefore ? (
                <TabsTrigger
                  value="before"
                  className={auditDetailTabTrigger(
                    'data-[state=active]:border-red-500/40 data-[state=active]:ring-2 data-[state=active]:ring-red-500/25',
                  )}
                >
                  Before
                </TabsTrigger>
              ) : null}
              {hasAfter ? (
                <TabsTrigger
                  value="after"
                  className={auditDetailTabTrigger(
                    'data-[state=active]:border-emerald-500/40 data-[state=active]:ring-2 data-[state=active]:ring-emerald-500/25',
                  )}
                >
                  After
                </TabsTrigger>
              ) : null}
            </TabsList>
            {hasDiff ? (
              <TabsContent value="diff" className="mt-0 min-h-0 flex-1">
                <JsonSnapshotDiff
                  before={entry.before_snapshot}
                  after={entry.after_snapshot}
                />
              </TabsContent>
            ) : null}
            {hasChanges ? (
              <TabsContent value="changes" className="mt-0 min-h-0 flex-1">
                <AuditJsonPanel
                  value={entry.changes}
                  label="Field changes"
                  variant="changes"
                />
              </TabsContent>
            ) : null}
            {hasBefore ? (
              <TabsContent value="before" className="mt-0 min-h-0 flex-1">
                <AuditJsonPanel
                  value={entry.before_snapshot}
                  label="Before snapshot"
                  variant="before"
                />
              </TabsContent>
            ) : null}
            {hasAfter ? (
              <TabsContent value="after" className="mt-0 min-h-0 flex-1">
                <AuditJsonPanel
                  value={entry.after_snapshot}
                  label="After snapshot"
                  variant="after"
                />
              </TabsContent>
            ) : null}
          </Tabs>
        ) : (
          <p className="text-sm text-muted-foreground">
            No change details recorded for this event.
          </p>
        )}
      </DialogContent>
    </Dialog>
  )
}
