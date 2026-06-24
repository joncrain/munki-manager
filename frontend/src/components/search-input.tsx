import { Search, X } from 'lucide-react'
import type { ChangeEvent, ComponentProps } from 'react'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

type SearchInputProps = Omit<ComponentProps<typeof Input>, 'type'> & {
  onClear?: () => void
  containerClassName?: string
}

export function SearchInput({
  value,
  onChange,
  onClear,
  className,
  containerClassName,
  ...props
}: SearchInputProps) {
  const hasValue = value != null && String(value).length > 0

  const handleClear = () => {
    if (onClear) {
      onClear()
      return
    }
    onChange?.({
      target: { value: '' },
    } as ChangeEvent<HTMLInputElement>)
  }

  return (
    <div className={cn('relative w-full max-w-sm', containerClassName)}>
      <Search
        className="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-muted-foreground"
        aria-hidden
      />
      <Input
        type="text"
        value={value}
        onChange={onChange}
        className={cn('pl-9 pr-9', className)}
        {...props}
      />
      <button
        type="button"
        className={cn(
          'absolute top-1/2 right-2 -translate-y-1/2 rounded-sm p-0.5 text-muted-foreground hover:text-foreground',
          !hasValue && 'pointer-events-none invisible',
        )}
        aria-label="Clear search"
        aria-hidden={!hasValue}
        tabIndex={hasValue ? 0 : -1}
        disabled={!hasValue}
        onClick={handleClear}
      >
        <X className="h-4 w-4" aria-hidden />
      </button>
    </div>
  )
}
