export const CUSTOM_RECENT_VALUE = 'recent_custom'
export const CUSTOM_INACTIVE_VALUE = 'inactive_custom'
export const DEFAULT_CUSTOM_CHECKIN_DAYS = 14
export const MAX_CHECKIN_FILTER_DAYS = 365

export type CheckinFilterOption = {
  value: string
  label: string
}

export type CheckinFilterGroup = {
  label: string
  options: CheckinFilterOption[]
}

export const CHECKIN_FILTER_GROUPS: CheckinFilterGroup[] = [
  {
    label: 'All',
    options: [{ value: '_all', label: 'All devices' }],
  },
  {
    label: 'Recently active',
    options: [
      { value: 'recent_7', label: 'Last 7 days' },
      { value: 'recent_30', label: 'Last 30 days' },
      { value: CUSTOM_RECENT_VALUE, label: 'Custom…' },
    ],
  },
  {
    label: 'Inactive',
    options: [
      { value: '7', label: 'Inactive 7+ days' },
      { value: '30', label: 'Inactive 30+ days' },
      { value: CUSTOM_INACTIVE_VALUE, label: 'Custom…' },
      { value: 'never', label: 'Never checked in' },
    ],
  },
]

export type ParsedCheckinFilter =
  | { mode: 'all' }
  | { mode: 'never' }
  | { mode: 'recent'; days: number }
  | { mode: 'inactive'; days: number }

const RECENT_FILTER_RE = /^recent_(\d+)$/
const INACTIVE_FILTER_RE = /^(\d+)$/

function clampCheckinDays(days: number): number {
  return Math.min(MAX_CHECKIN_FILTER_DAYS, Math.max(1, Math.round(days)))
}

export function parseCheckinFilter(
  raw: string | null | undefined,
): ParsedCheckinFilter {
  if (!raw || raw === '_all') {
    return { mode: 'all' }
  }
  if (raw === 'never') {
    return { mode: 'never' }
  }

  const recentMatch = raw.match(RECENT_FILTER_RE)
  if (recentMatch) {
    const days = Number(recentMatch[1])
    if (days >= 1 && days <= MAX_CHECKIN_FILTER_DAYS) {
      return { mode: 'recent', days }
    }
  }

  const inactiveMatch = raw.match(INACTIVE_FILTER_RE)
  if (inactiveMatch) {
    const days = Number(inactiveMatch[1])
    if (days >= 1 && days <= MAX_CHECKIN_FILTER_DAYS) {
      return { mode: 'inactive', days }
    }
  }

  return { mode: 'all' }
}

export function serializeCheckinFilter(
  filter: ParsedCheckinFilter,
): string | null {
  switch (filter.mode) {
    case 'all':
      return null
    case 'never':
      return 'never'
    case 'recent':
      return `recent_${filter.days}`
    case 'inactive':
      return String(filter.days)
  }
}

export function checkinFilterSelectValue(filter: ParsedCheckinFilter): string {
  if (filter.mode === 'all') return '_all'
  if (filter.mode === 'never') return 'never'
  if (filter.mode === 'recent') {
    if (filter.days === 7) return 'recent_7'
    if (filter.days === 30) return 'recent_30'
    return CUSTOM_RECENT_VALUE
  }
  if (filter.days === 7) return '7'
  if (filter.days === 30) return '30'
  return CUSTOM_INACTIVE_VALUE
}

export function checkinFilterLabel(filter: ParsedCheckinFilter): string {
  switch (filter.mode) {
    case 'all':
      return 'All devices'
    case 'never':
      return 'Never checked in'
    case 'recent':
      return `Checked in last ${filter.days} days`
    case 'inactive':
      return `Inactive ${filter.days}+ days`
  }
}

export function checkinFilterApiParams(
  filter: ParsedCheckinFilter,
): URLSearchParams {
  const params = new URLSearchParams()
  if (filter.mode === 'never') {
    params.set('no_checkin', 'true')
  } else if (filter.mode === 'recent') {
    params.set('recent_days', String(filter.days))
  } else if (filter.mode === 'inactive') {
    params.set('stale_days', String(filter.days))
  }
  return params
}

export function checkinFilterFromSelectValue(
  value: string,
  current: ParsedCheckinFilter,
): ParsedCheckinFilter | null {
  if (value === '_all') return { mode: 'all' }
  if (value === 'never') return { mode: 'never' }
  if (value === 'recent_7') return { mode: 'recent', days: 7 }
  if (value === 'recent_30') return { mode: 'recent', days: 30 }
  if (value === CUSTOM_RECENT_VALUE) {
    const days =
      current.mode === 'recent' && current.days !== 7 && current.days !== 30
        ? current.days
        : DEFAULT_CUSTOM_CHECKIN_DAYS
    return { mode: 'recent', days }
  }
  if (value === '7') return { mode: 'inactive', days: 7 }
  if (value === '30') return { mode: 'inactive', days: 30 }
  if (value === CUSTOM_INACTIVE_VALUE) {
    const days =
      current.mode === 'inactive' && current.days !== 7 && current.days !== 30
        ? current.days
        : DEFAULT_CUSTOM_CHECKIN_DAYS
    return { mode: 'inactive', days }
  }
  return null
}

export function checkinFilterWithCustomDays(
  filter: ParsedCheckinFilter,
  rawDays: string,
): ParsedCheckinFilter | null {
  const days = clampCheckinDays(Number(rawDays))
  if (!Number.isFinite(days) || days < 1) return null

  if (filter.mode === 'recent') {
    return { mode: 'recent', days }
  }
  if (filter.mode === 'inactive') {
    return { mode: 'inactive', days }
  }
  return null
}

export function isCustomCheckinFilter(filter: ParsedCheckinFilter): boolean {
  return (
    (filter.mode === 'recent' && filter.days !== 7 && filter.days !== 30) ||
    (filter.mode === 'inactive' && filter.days !== 7 && filter.days !== 30)
  )
}
