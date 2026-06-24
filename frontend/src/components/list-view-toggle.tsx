import { LayoutGrid, Table2 } from 'lucide-react'
import { Button } from '@/components/ui/button'

export type ListViewMode = 'cards' | 'table'

interface ListViewToggleProps {
  value: ListViewMode
  onChange: (value: ListViewMode) => void
}

export function ListViewToggle({ value, onChange }: ListViewToggleProps) {
  return (
    <div className="inline-flex items-center rounded-md border bg-muted/30 p-0.5">
      <Button
        type="button"
        variant={value === 'cards' ? 'secondary' : 'ghost'}
        size="sm"
        className="h-8 gap-1.5 px-2.5"
        aria-pressed={value === 'cards'}
        aria-label="Card layout"
        onClick={() => onChange('cards')}
      >
        <LayoutGrid className="h-4 w-4" aria-hidden />
        Cards
      </Button>
      <Button
        type="button"
        variant={value === 'table' ? 'secondary' : 'ghost'}
        size="sm"
        className="h-8 gap-1.5 px-2.5"
        aria-pressed={value === 'table'}
        aria-label="Table layout"
        onClick={() => onChange('table')}
      >
        <Table2 className="h-4 w-4" aria-hidden />
        Table
      </Button>
    </div>
  )
}
