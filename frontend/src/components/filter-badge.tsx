import type { VariantProps } from 'class-variance-authority'
import { X } from 'lucide-react'
import type { KeyboardEvent, MouseEvent, ReactNode } from 'react'
import { Badge, type badgeVariants } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

type FilterBadgeProps = {
  children: ReactNode
  onFilter: () => void
  ariaLabel: string
  title?: string
  variant?: VariantProps<typeof badgeVariants>['variant']
  className?: string
}

function handleFilterActivation(
  event: MouseEvent<HTMLElement> | KeyboardEvent<HTMLElement>,
  onFilter: () => void,
) {
  event.preventDefault()
  event.stopPropagation()
  onFilter()
}

export function FilterBadge({
  children,
  onFilter,
  ariaLabel,
  title,
  variant,
  className,
}: FilterBadgeProps) {
  return (
    <Badge
      variant={variant}
      role="button"
      tabIndex={0}
      title={title}
      className={cn(
        'relative z-10 cursor-pointer transition-opacity hover:opacity-80',
        className,
      )}
      onClick={(event) => handleFilterActivation(event, onFilter)}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          handleFilterActivation(event, onFilter)
        }
      }}
      aria-label={ariaLabel}
    >
      {children}
    </Badge>
  )
}

export type ActiveFilterChip = {
  id: string
  label: string
  onRemove: () => void
}

export function ActiveFilterBadges({
  filters,
  className,
}: {
  filters: ActiveFilterChip[]
  className?: string
}) {
  if (filters.length === 0) return null

  return (
    <div
      className={cn(
        'flex min-w-0 flex-wrap items-center justify-end gap-1.5',
        className,
      )}
    >
      {filters.map((filter) => (
        <Badge
          key={filter.id}
          variant="secondary"
          className="max-w-full gap-1 pr-1 font-normal"
        >
          <span className="truncate">{filter.label}</span>
          <button
            type="button"
            className="shrink-0 rounded-full p-0.5 hover:bg-background/30"
            onClick={filter.onRemove}
            aria-label={`Remove ${filter.label} filter`}
          >
            <X className="size-3" aria-hidden="true" />
          </button>
        </Badge>
      ))}
    </div>
  )
}
