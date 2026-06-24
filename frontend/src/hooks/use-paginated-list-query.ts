import { useQuery } from '@tanstack/react-query'
import { parseAsInteger, useQueryState } from 'nuqs'
import { useCallback, useMemo } from 'react'
import { api, type PaginatedResponse } from '@/lib/api'

interface UsePaginatedListQueryOptions {
  /** First segment(s) of the React Query key, before page and pageSize. */
  queryKeyPrefix: readonly unknown[]
  /** API path without query string, e.g. `/audit`. */
  path: string
  defaultPageSize?: number
  /** Extra query-key segments after page and pageSize (filter values, etc.). */
  filterKey?: readonly unknown[]
  /** Append non-pagination search params before the request. */
  appendSearchParams?: (params: URLSearchParams) => void
  enabled?: boolean
}

export function usePaginatedListQuery<T>({
  queryKeyPrefix,
  path,
  defaultPageSize = 50,
  filterKey = [],
  appendSearchParams,
  enabled = true,
}: UsePaginatedListQueryOptions) {
  const [page, setPage] = useQueryState('page', parseAsInteger.withDefault(1))
  const [pageSize, setPageSize] = useQueryState(
    'pageSize',
    parseAsInteger.withDefault(defaultPageSize),
  )

  const queryKey = useMemo(
    () => [...queryKeyPrefix, page, pageSize, ...filterKey],
    [queryKeyPrefix, page, pageSize, filterKey],
  )

  const query = useQuery({
    queryKey,
    queryFn: () => {
      const params = new URLSearchParams()
      params.set('page', String(page))
      params.set('page_size', String(pageSize))
      appendSearchParams?.(params)
      return api.get<PaginatedResponse<T>>(`${path}?${params.toString()}`)
    },
    enabled,
  })

  const resetPage = useCallback(() => {
    void setPage(1)
  }, [setPage])

  const onPageSizeChange = useCallback(
    (size: number) => {
      void setPageSize(size)
      void setPage(1)
    },
    [setPage, setPageSize],
  )

  return {
    page,
    pageSize,
    setPage,
    setPageSize,
    resetPage,
    onPageSizeChange,
    data: query.data,
    isLoading: query.isLoading,
    query,
  }
}
