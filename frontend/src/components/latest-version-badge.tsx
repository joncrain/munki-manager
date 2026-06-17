import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

export function LatestVersionBadge({ className }: { className?: string }) {
  return (
    <Badge
      variant="secondary"
      className={cn(
        'shrink-0 px-1.5 py-0 text-[10px] font-medium uppercase tracking-wide',
        className,
      )}
    >
      Latest
    </Badge>
  )
}

export function VersionWithLatestBadge({
  version,
  isLatest,
  className,
  versionClassName,
}: {
  version: string | null | undefined
  isLatest?: boolean
  className?: string
  versionClassName?: string
}) {
  if (!version) return <>—</>
  return (
    <span className={cn('inline-flex items-center gap-1.5', className)}>
      <span className={cn('font-mono text-sm', versionClassName)}>
        {version}
      </span>
      {isLatest ? <LatestVersionBadge /> : null}
    </span>
  )
}
