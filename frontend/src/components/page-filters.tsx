import { Filter, X } from 'lucide-react'
import { type ReactNode, useState } from 'react'
import {
  ActiveFilterBadges,
  type ActiveFilterChip,
} from '@/components/filter-badge'
import { Label } from '@/components/ui/label'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { useIsMobile } from '@/hooks/use-mobile'
import { cn } from '@/lib/utils'

type PageFiltersProps = {
  /** Filter controls shown in the sheet (search stays in the toolbar via `search`). */
  children: ReactNode
  /** Search input rendered in the top bar (not in the sheet). */
  search?: ReactNode
  isFiltered?: boolean
  activeFilterCount?: number
  onClear?: () => void
  activeFilters?: ActiveFilterChip[]
  trailing?: ReactNode
  className?: string
  sheetDescription?: string
}

export function FilterSheetField({
  label,
  hasValue = false,
  onClear,
  children,
}: {
  label: string
  hasValue?: boolean
  onClear?: () => void
  children: ReactNode
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-2">
        <Label className="text-sm font-medium">{label}</Label>
        {hasValue && onClear ? (
          <button
            type="button"
            className="rounded-sm p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
            aria-label={`Clear ${label} filter`}
            onClick={onClear}
          >
            <X className="size-3.5" aria-hidden />
          </button>
        ) : null}
      </div>
      {children}
    </div>
  )
}

function FilterSheetButton({
  count,
  isFiltered,
  onClear,
  onOpen,
}: {
  count: number
  isFiltered: boolean
  onClear?: () => void
  onOpen: () => void
}) {
  return (
    <div className="inline-flex h-8 items-stretch overflow-hidden rounded-md border bg-background shadow-xs">
      <button
        type="button"
        className="flex h-full items-center gap-1.5 px-2.5 text-sm hover:bg-accent hover:text-accent-foreground"
        onClick={onOpen}
      >
        <Filter className="size-4 shrink-0" aria-hidden="true" />
        Filters{count > 0 ? ` (${count})` : ''}
      </button>
      {isFiltered && onClear ? (
        <>
          <span className="w-px self-stretch bg-border" aria-hidden="true" />
          <button
            type="button"
            className="flex h-full items-center px-2 hover:bg-accent hover:text-accent-foreground"
            aria-label="Clear filters"
            onClick={onClear}
          >
            <X className="size-3.5" />
          </button>
        </>
      ) : null}
    </div>
  )
}

export function PageFilters({
  children,
  search,
  isFiltered = false,
  activeFilterCount = 0,
  onClear,
  activeFilters = [],
  trailing,
  className,
  sheetDescription = 'Refine the list with one or more filters.',
}: PageFiltersProps) {
  const isMobile = useIsMobile()
  const [open, setOpen] = useState(false)
  const count = activeFilterCount > 0 ? activeFilterCount : isFiltered ? 1 : 0

  return (
    <div className={cn('flex w-full items-center gap-2', className)}>
      {search ? <div className="min-w-0 shrink">{search}</div> : null}

      <div className="ml-auto flex min-w-0 items-center gap-2">
        <ActiveFilterBadges filters={activeFilters} />
        <Sheet open={open} onOpenChange={setOpen}>
          <FilterSheetButton
            count={count}
            isFiltered={isFiltered}
            onClear={onClear}
            onOpen={() => setOpen(true)}
          />
          <SheetContent
            side={isMobile ? 'bottom' : 'right'}
            className={cn(
              isMobile ? 'max-h-[85vh] overflow-y-auto' : 'w-full sm:max-w-md',
            )}
          >
            <SheetHeader>
              <SheetTitle>Filters</SheetTitle>
              <SheetDescription>{sheetDescription}</SheetDescription>
            </SheetHeader>
            <div className="flex flex-col gap-4 px-4 pb-4 [&_button[role=combobox]]:w-full [&_input]:w-full">
              {children}
            </div>
          </SheetContent>
        </Sheet>
        {trailing}
      </div>
    </div>
  )
}
