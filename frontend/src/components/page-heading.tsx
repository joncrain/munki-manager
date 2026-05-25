import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import type { MunkiAccentKey } from '@/lib/munki-accents'
import { munkiAccents } from '@/lib/munki-accents'
import { cn } from '@/lib/utils'

type PageHeadingProps = {
  icon: LucideIcon
  accent: MunkiAccentKey
  title: string
  /** Rendered beside the title (badges, counts). */
  afterTitle?: ReactNode
  /**
   * Optional action cluster (buttons, dropdowns) rendered to the right of
   * the title on `sm+` and below the title on mobile. Pass a fragment with
   * one or more buttons; this component takes care of wrapping/stacking so
   * pages don't have to roll their own ``flex justify-between`` row that
   * forgets ``flex-wrap`` and overflows on 375px viewports.
   */
  actions?: ReactNode
  className?: string
}

/**
 * Page title with the same Lucide icon + accent treatment as the app sidebar.
 *
 * On narrow viewports the title scales down (`text-2xl`) and any ``actions``
 * stack underneath; at `sm+` the title returns to `text-3xl` and actions sit
 * on the right.
 */
export function PageHeading({
  icon: Icon,
  accent,
  title,
  afterTitle,
  actions,
  className,
}: PageHeadingProps) {
  const a = munkiAccents[accent]

  const heading = (
    <div
      className={cn('flex min-w-0 items-center gap-2 sm:gap-3', a.pageTitle)}
    >
      <Icon
        className={cn('h-6 w-6 shrink-0 sm:h-8 sm:w-8', a.icon)}
        aria-hidden
      />
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <h1 className="text-pretty text-2xl font-bold sm:text-3xl">{title}</h1>
        {afterTitle}
      </div>
    </div>
  )

  if (!actions) {
    return <div className={cn('min-w-0', className)}>{heading}</div>
  }

  return (
    <div
      className={cn(
        'flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between',
        className,
      )}
    >
      {heading}
      <div className="flex flex-wrap items-center gap-2 sm:shrink-0">
        {actions}
      </div>
    </div>
  )
}
