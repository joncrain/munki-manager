import {
  AlertCircle,
  CheckCircle2,
  Download,
  MinusCircle,
  ShieldAlert,
} from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

/** AutoPkg run result status for approval-queue rows (semantic styling like trust badges). */
export function RunResultStatusBadge({
  status,
  className,
}: {
  status: string
  className?: string
}) {
  switch (status) {
    case 'imported':
      return (
        <Badge
          variant="default"
          className={cn(
            'shrink-0 bg-gruvbox-orange text-primary-foreground hover:bg-gruvbox-orange/90',
            className,
          )}
        >
          <Download className="size-3.5" aria-hidden />
          Imported
        </Badge>
      )
    case 'trust_failed':
      return (
        <Badge variant="destructive" className={cn('shrink-0', className)}>
          <ShieldAlert className="size-3.5" aria-hidden />
          Trust failed
        </Badge>
      )
    case 'failed':
      return (
        <Badge variant="destructive" className={cn('shrink-0', className)}>
          <AlertCircle className="size-3.5" aria-hidden />
          Failed
        </Badge>
      )
    case 'success':
      return (
        <Badge
          variant="default"
          className={cn(
            'shrink-0 bg-gruvbox-green text-primary-foreground hover:bg-gruvbox-green/90',
            className,
          )}
        >
          <CheckCircle2 className="size-3.5" aria-hidden />
          Success
        </Badge>
      )
    case 'no_change':
      return (
        <Badge variant="secondary" className={cn('shrink-0', className)}>
          <MinusCircle className="size-3.5" aria-hidden />
          No change
        </Badge>
      )
    default:
      return (
        <Badge variant="secondary" className={cn('shrink-0', className)}>
          {status}
        </Badge>
      )
  }
}
