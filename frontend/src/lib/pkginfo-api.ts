import { api, type PaginatedResponse, type PkgInfoSummary } from '@/lib/api'

const PKGINFO_PAGE_SIZE = 200

/** Load every latest pkginfo row for software pickers (paginated under the hood). */
export async function fetchPkginfoForPicker(
  search?: string,
): Promise<PkgInfoSummary[]> {
  const params = new URLSearchParams()
  params.set('page', '1')
  params.set('page_size', String(PKGINFO_PAGE_SIZE))
  params.set('latest_only', 'true')
  params.set('sort_by', 'name')
  params.set('sort_order', 'asc')
  const trimmed = search?.trim()
  if (trimmed) {
    params.set('search', trimmed)
  }

  const first = await api.get<PaginatedResponse<PkgInfoSummary>>(
    `/pkginfo?${params.toString()}`,
  )
  const out = [...first.items]
  for (let p = 2; p <= first.total_pages; p++) {
    params.set('page', String(p))
    const next = await api.get<PaginatedResponse<PkgInfoSummary>>(
      `/pkginfo?${params.toString()}`,
    )
    out.push(...next.items)
  }
  return out
}
