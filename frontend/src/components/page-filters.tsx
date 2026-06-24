import { Filter, X } from 'lucide-react'
import { type ReactNode, useState } from 'react'
import { Button } from '@/components/ui/button'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/components/ui/sheet'
import { useIsMobile } from '@/hooks/use-mobile'
import { cn } from '@/lib/utils'

type PageFiltersProps = {
  children: ReactNode
  isFiltered?: boolean
  activeFilterCount?: number
  onClear?: () => void
  trailing?: ReactNode
  className?: string
  sheetDescription?: string
}

function ClearFiltersButton({ onClear }: { onClear: () => void }) {
  return (
    <Button
      variant="ghost"
      size="sm"
      aria-label="Clear filters"
      onClick={onClear}
    >
      <X className="h-4 w-4" />
      Clear
    </Button>
  )
}

export function PageFilters({
  children,
  isFiltered = false,
  activeFilterCount = 0,
  onClear,
  trailing,
  className,
  sheetDescription = 'Refine the list with one or more filters.',
}: PageFiltersProps) {
  const isMobile = useIsMobile()
  const [open, setOpen] = useState(false)
  const count = activeFilterCount > 0 ? activeFilterCount : isFiltered ? 1 : 0

  if (isMobile) {
    return (
      <div className={cn('flex w-full items-center gap-2', className)}>
        <Sheet open={open} onOpenChange={setOpen}>
          <SheetTrigger asChild>
            <Button variant="outline" size="sm" className="shrink-0">
              <Filter className="h-4 w-4" />
              Filters{count > 0 ? ` (${count})` : ''}
            </Button>
          </SheetTrigger>
          <SheetContent side="bottom" className="max-h-[85vh] overflow-y-auto">
            <SheetHeader>
              <SheetTitle>Filters</SheetTitle>
              <SheetDescription>{sheetDescription}</SheetDescription>
            </SheetHeader>
            <div className="flex flex-col gap-3 px-4 pb-4 [&_button[role=combobox]]:w-full [&_input]:w-full">
              {children}
            </div>
            {isFiltered && onClear ? (
              <div className="border-t px-4 py-3">
                <ClearFiltersButton onClear={onClear} />
              </div>
            ) : null}
          </SheetContent>
        </Sheet>
        {trailing ? <div className="ml-auto shrink-0">{trailing}</div> : null}
      </div>
    )
  }

  return (
    <div className={cn('flex w-full flex-wrap items-center gap-2', className)}>
      <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
        {children}
      </div>
      {isFiltered && onClear ? <ClearFiltersButton onClear={onClear} /> : null}
      {trailing ? <div className="ml-auto shrink-0">{trailing}</div> : null}
    </div>
  )
}
