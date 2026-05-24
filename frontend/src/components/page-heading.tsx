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
  className?: string
}

/** Page title with the same Lucide icon + accent treatment as the app sidebar. */
export function PageHeading({
  icon: Icon,
  accent,
  title,
  afterTitle,
  className,
}: PageHeadingProps) {
  const a = munkiAccents[accent]
  return (
    <div
      className={cn('flex min-w-0 items-center gap-3', a.pageTitle, className)}
    >
      <Icon className={cn('h-8 w-8 shrink-0', a.icon)} aria-hidden />
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <h1 className="text-3xl font-bold text-pretty">{title}</h1>
        {afterTitle}
      </div>
    </div>
  )
}
