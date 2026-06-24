import {
  type AuditLogRead,
  type AutoPkgRecipeRead,
  api,
  type ClientMachineSummary,
  type PaginatedResponse,
  type PkgInfoSummary,
} from '@/lib/api'

export type EntitySearchType = 'software' | 'autopkg' | 'device' | 'audit'
export type SearchScope = 'all' | EntitySearchType

export interface QuickCheckResult {
  count: number
  id: string | null
}

function buildParams(search: string, pageSize: number) {
  const params = new URLSearchParams()
  params.set('page', '1')
  params.set('page_size', String(pageSize))
  if (search.trim()) {
    params.set('search', search.trim())
  }
  return params
}

export async function suggestSoftware(
  q: string,
  limit = 5,
): Promise<PkgInfoSummary[]> {
  const params = buildParams(q, limit)
  const res = await api.get<PaginatedResponse<PkgInfoSummary>>(
    `/pkginfo?${params.toString()}`,
  )
  return res.items
}

export async function suggestAutopkg(
  q: string,
  limit = 5,
): Promise<AutoPkgRecipeRead[]> {
  const params = buildParams(q, limit)
  const res = await api.get<PaginatedResponse<AutoPkgRecipeRead>>(
    `/autopkg/recipes?${params.toString()}`,
  )
  return res.items
}

export async function suggestDevices(
  q: string,
  limit = 5,
): Promise<ClientMachineSummary[]> {
  const params = buildParams(q, limit)
  const res = await api.get<PaginatedResponse<ClientMachineSummary>>(
    `/reports/machines?${params.toString()}`,
  )
  return res.items
}

export async function suggestAudit(
  q: string,
  limit = 5,
): Promise<AuditLogRead[]> {
  const params = buildParams(q, limit)
  const res = await api.get<PaginatedResponse<AuditLogRead>>(
    `/audit?${params.toString()}`,
  )
  return res.items
}

export async function quickCheckSoftware(q: string): Promise<QuickCheckResult> {
  const params = buildParams(q, 2)
  const res = await api.get<PaginatedResponse<PkgInfoSummary>>(
    `/pkginfo?${params.toString()}`,
  )
  return {
    count: res.total,
    id: res.total === 1 ? (res.items[0]?.id ?? null) : null,
  }
}

export async function quickCheckAutopkg(q: string): Promise<QuickCheckResult> {
  const params = buildParams(q, 2)
  const res = await api.get<PaginatedResponse<AutoPkgRecipeRead>>(
    `/autopkg/recipes?${params.toString()}`,
  )
  return {
    count: res.total,
    id: res.total === 1 ? (res.items[0]?.id ?? null) : null,
  }
}

export async function quickCheckDevice(q: string): Promise<QuickCheckResult> {
  const params = buildParams(q, 2)
  const res = await api.get<PaginatedResponse<ClientMachineSummary>>(
    `/reports/machines?${params.toString()}`,
  )
  return {
    count: res.total,
    id: res.total === 1 ? (res.items[0]?.id ?? null) : null,
  }
}

export function softwareDetailPath(id: string) {
  return `/software/${id}`
}

export function autopkgDetailPath(id: string) {
  return `/autopkg/recipes/${id}`
}

export function deviceDetailPath(id: string) {
  return `/reporting/devices/${id}`
}

export function softwareListPath(_q: string) {
  return '/software'
}

export function autopkgListPath(_q: string) {
  return '/autopkg/recipes'
}

export function deviceListPath(q: string) {
  return `/reporting?q=${encodeURIComponent(q)}`
}

export function auditListPath(q: string) {
  return `/audit?search=${encodeURIComponent(q)}`
}
