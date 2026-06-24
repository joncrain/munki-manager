import { AlertTriangle, ChevronRight, EyeOff, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import { cn } from '@/lib/utils'

const DISMISS_STORAGE_KEY = 'dashboard-attention-dismissed'

export type AttentionItem = {
  id: string
  label: string
  href: string
  count: number
  tone?: 'default' | 'warning' | 'danger'
}

function highestTone(
  items: AttentionItem[],
): NonNullable<AttentionItem['tone']> {
  if (items.some((item) => item.tone === 'danger')) return 'danger'
  if (items.some((item) => item.tone === 'warning')) return 'warning'
  return 'default'
}

function triggerClass(tone: NonNullable<AttentionItem['tone']>) {
  switch (tone) {
    case 'danger':
      return 'border-destructive/35 bg-destructive/10 text-destructive hover:bg-destructive/15 dark:text-destructive'
    case 'warning':
      return 'border-gruvbox-yellow/40 bg-gruvbox-yellow/10 text-gruvbox-yellow hover:bg-gruvbox-yellow/15'
    default:
      return 'border-border bg-muted/40 text-muted-foreground hover:bg-muted/60 hover:text-foreground'
  }
}

function countBadgeClass(tone: AttentionItem['tone']) {
  switch (tone) {
    case 'danger':
      return 'bg-destructive/15 text-destructive'
    case 'warning':
      return 'bg-gruvbox-yellow/15 text-gruvbox-yellow'
    default:
      return 'bg-muted text-muted-foreground'
  }
}

function AttentionRow({ item }: { item: AttentionItem }) {
  return (
    <Link
      to={item.href}
      className="group flex items-center gap-3 rounded-md px-2 py-2 text-sm transition-colors hover:bg-muted/60"
    >
      <span className="min-w-0 flex-1 truncate font-medium text-foreground">
        {item.label}
      </span>
      <Badge
        variant="secondary"
        className={cn('tabular-nums', countBadgeClass(item.tone))}
      >
        {item.count}
      </Badge>
      <ChevronRight
        className="size-4 shrink-0 text-muted-foreground/50 transition-transform group-hover:translate-x-0.5 group-hover:text-muted-foreground"
        aria-hidden
      />
    </Link>
  )
}

/** Dashboard alert badge — pass as ``PageHeading`` ``actions`` for right alignment. */
export function NeedsAttentionStrip({ items }: { items: AttentionItem[] }) {
  const [dismissed, setDismissed] = useState(false)
  const [open, setOpen] = useState(false)

  useEffect(() => {
    setDismissed(localStorage.getItem(DISMISS_STORAGE_KEY) === '1')
  }, [])

  if (!items.length) {
    return null
  }

  const tone = highestTone(items)
  const totalCount = items.reduce((sum, item) => sum + item.count, 0)

  function dismiss() {
    localStorage.setItem(DISMISS_STORAGE_KEY, '1')
    setDismissed(true)
    setOpen(false)
  }

  function restore() {
    localStorage.removeItem(DISMISS_STORAGE_KEY)
    setDismissed(false)
  }

  if (dismissed) {
    return (
      <button
        type="button"
        onClick={restore}
        className="inline-flex items-center gap-1 rounded-full border border-dashed border-border/80 px-2.5 py-0.5 text-xs text-muted-foreground transition-colors hover:border-border hover:bg-muted/40 hover:text-foreground"
      >
        <EyeOff className="size-3" aria-hidden />
        {items.length} hidden
      </button>
    )
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={cn(
            'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium transition-colors',
            triggerClass(tone),
          )}
          aria-expanded={open}
          aria-haspopup="dialog"
        >
          <AlertTriangle className="size-3 shrink-0" aria-hidden />
          <span>
            {items.length} need attention
            {totalCount > items.length ? (
              <span className="opacity-70"> · {totalCount}</span>
            ) : null}
          </span>
        </button>
      </PopoverTrigger>
      <PopoverContent
        align="end"
        sideOffset={8}
        className="w-[min(100vw-2rem,20rem)] p-0"
      >
        <div className="flex items-center justify-between gap-2 border-b px-3 py-2.5">
          <p className="text-sm font-medium text-foreground">Needs attention</p>
          <Button
            type="button"
            variant="ghost"
            size="icon-xs"
            className="text-muted-foreground"
            onClick={dismiss}
            aria-label="Hide attention alerts"
          >
            <X className="size-3.5" aria-hidden />
          </Button>
        </div>
        <ul className="list-none p-1">
          {items.map((item) => (
            <li key={item.id}>
              <AttentionRow item={item} />
            </li>
          ))}
        </ul>
        <div className="border-t px-3 py-2">
          <button
            type="button"
            onClick={dismiss}
            className="text-xs text-muted-foreground transition-colors hover:text-foreground"
          >
            Hide alerts
          </button>
        </div>
      </PopoverContent>
    </Popover>
  )
}
