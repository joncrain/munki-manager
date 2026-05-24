import { type AutoPkgRecipeRead, api, type PaginatedResponse } from '@/lib/api'

const FETCH_PAGE_SIZE = 500

/** Load every AutoPkg recipe (paginated under the hood). */
export async function fetchAllAutopkgRecipes(): Promise<AutoPkgRecipeRead[]> {
  const first = await api.get<PaginatedResponse<AutoPkgRecipeRead>>(
    `/autopkg/recipes?page=1&page_size=${FETCH_PAGE_SIZE}`,
  )
  const out = [...first.items]
  for (let p = 2; p <= first.total_pages; p++) {
    const next = await api.get<PaginatedResponse<AutoPkgRecipeRead>>(
      `/autopkg/recipes?page=${p}&page_size=${FETCH_PAGE_SIZE}`,
    )
    out.push(...next.items)
  }
  return out
}

/** Enabled overrides only (paginated under the hood). */
export async function fetchEnabledAutopkgRecipes(): Promise<
  AutoPkgRecipeRead[]
> {
  const first = await api.get<PaginatedResponse<AutoPkgRecipeRead>>(
    `/autopkg/recipes?enabled_only=true&page=1&page_size=${FETCH_PAGE_SIZE}`,
  )
  const out = [...first.items]
  for (let p = 2; p <= first.total_pages; p++) {
    const next = await api.get<PaginatedResponse<AutoPkgRecipeRead>>(
      `/autopkg/recipes?enabled_only=true&page=${p}&page_size=${FETCH_PAGE_SIZE}`,
    )
    out.push(...next.items)
  }
  return out
}
