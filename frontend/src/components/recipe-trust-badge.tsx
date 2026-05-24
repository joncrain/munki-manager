import { ShieldAlert, ShieldCheck, ShieldQuestion } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

/**
 * Prominent trust status for recipe headers (detail page, cards). Matches list styling.
 */
export function RecipeTrustStatusBadge({
  status,
  className,
}: {
  status: string
  className?: string
}) {
  switch (status) {
    case 'verified':
      return (
        <Badge
          variant="default"
          className={cn(
            'shrink-0 bg-gruvbox-green text-primary-foreground hover:bg-gruvbox-green/90',
            className,
          )}
        >
          <ShieldCheck className="size-3.5" aria-hidden />
          Trust verified
        </Badge>
      )
    case 'failed':
      return (
        <Badge variant="destructive" className={cn('shrink-0', className)}>
          <ShieldAlert className="size-3.5" aria-hidden />
          Trust failed
        </Badge>
      )
    case 'pending_approval':
      return (
        <Badge
          asChild
          variant="default"
          className={cn(
            'shrink-0 bg-gruvbox-yellow text-primary-foreground hover:bg-gruvbox-yellow/90',
            className,
          )}
        >
          <Link
            to="/approvals"
            className="inline-flex items-center gap-1.5"
            title="Review on Approvals"
          >
            <ShieldAlert className="size-3.5" aria-hidden />
            Trust approval pending
          </Link>
        </Badge>
      )
    default:
      return (
        <Badge variant="secondary" className={cn('shrink-0', className)}>
          <ShieldQuestion className="size-3.5" aria-hidden />
          Trust unknown
        </Badge>
      )
  }
}
