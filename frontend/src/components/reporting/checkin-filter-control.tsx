import { useMemo } from 'react'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  CHECKIN_FILTER_GROUPS,
  CUSTOM_INACTIVE_VALUE,
  CUSTOM_RECENT_VALUE,
  checkinFilterFromSelectValue,
  checkinFilterLabel,
  checkinFilterSelectValue,
  checkinFilterWithCustomDays,
  parseCheckinFilter,
  serializeCheckinFilter,
} from '@/lib/reporting-device-filters'

export function CheckinFilterControl({
  value,
  onChange,
  onApply,
}: {
  value: string
  onChange: (next: string | null) => void
  onApply?: () => void
}) {
  const filter = useMemo(() => parseCheckinFilter(value), [value])
  const selectValue = checkinFilterSelectValue(filter)
  const showCustomDays =
    selectValue === CUSTOM_RECENT_VALUE || selectValue === CUSTOM_INACTIVE_VALUE

  function applyFilter(next: ReturnType<typeof parseCheckinFilter>) {
    onChange(serializeCheckinFilter(next))
    onApply?.()
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Select
        value={selectValue}
        onValueChange={(next) => {
          const parsed = checkinFilterFromSelectValue(next, filter)
          if (parsed) applyFilter(parsed)
        }}
      >
        <SelectTrigger
          className="w-full md:w-[220px]"
          aria-label="Check-in activity"
        >
          <SelectValue placeholder="Check-in activity">
            {checkinFilterLabel(filter)}
          </SelectValue>
        </SelectTrigger>
        <SelectContent>
          {CHECKIN_FILTER_GROUPS.map((group, groupIndex) => (
            <SelectGroup key={group.label}>
              {groupIndex > 0 ? <SelectSeparator /> : null}
              <SelectLabel>{group.label}</SelectLabel>
              {group.options.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectGroup>
          ))}
        </SelectContent>
      </Select>

      {showCustomDays && filter.mode !== 'all' && filter.mode !== 'never' ? (
        <div className="flex items-center gap-2">
          <Input
            type="number"
            min={1}
            max={365}
            inputMode="numeric"
            value={String(filter.days)}
            onChange={(event) => {
              const next = checkinFilterWithCustomDays(
                filter,
                event.target.value,
              )
              if (next) applyFilter(next)
            }}
            className="w-20"
            aria-label={
              filter.mode === 'recent'
                ? 'Custom recent check-in days'
                : 'Custom inactive check-in days'
            }
          />
          <span className="text-sm text-muted-foreground">days</span>
        </div>
      ) : null}
    </div>
  )
}

export function checkinFilterIsActive(value: string): boolean {
  return parseCheckinFilter(value).mode !== 'all'
}

export function checkinFilterActiveCount(value: string): number {
  return checkinFilterIsActive(value) ? 1 : 0
}
