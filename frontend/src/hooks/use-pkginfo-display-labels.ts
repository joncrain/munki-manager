import { useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'
import { api, type PaginatedResponse, type PkgInfoSummary } from '@/lib/api'
import { parseManifestItemRef } from '@/lib/manifest-item-ref'

/** Resolve manifest item refs (incl. pinned `name-version`) to pkginfo display_name. */
export function usePkginfoDisplayLabels(names: string[]) {
  const uniqueRaw = useMemo(
    () => [...new Set(names)].sort(),
    [names.join('\0')],
  )

  const uniqueBases = useMemo(() => {
    const s = new Set<string>()
    for (const raw of uniqueRaw) {
      s.add(parseManifestItemRef(raw).baseName)
    }
    return [...s].sort()
  }, [uniqueRaw.join('\0')])

  return useQuery({
    queryKey: ['pkginfo-display-labels', uniqueRaw.join('\0')],
    queryFn: async () => {
      const byBase: Record<string, string> = {}
      await Promise.all(
        uniqueBases.map(async (base) => {
          try {
            const res = await api.get<PaginatedResponse<PkgInfoSummary>>(
              `/pkginfo?name=${encodeURIComponent(base)}&page_size=1`,
            )
            const pkg = res.items[0]
            const d = pkg?.display_name?.trim()
            byBase[base] = d || base
          } catch {
            byBase[base] = base
          }
        }),
      )
      const out: Record<string, string> = {}
      for (const raw of uniqueRaw) {
        const { baseName } = parseManifestItemRef(raw)
        out[raw] = byBase[baseName] ?? raw
      }
      return out
    },
    enabled: uniqueRaw.length > 0,
    staleTime: 5 * 60 * 1000,
  })
}

export interface PkginfoInstallReportLink {
  displayName: string
  pkginfoId: string | null
}

function installReportLinkKey(name: string, version: string | null) {
  return `${name}\0${version ?? ''}`
}

/** Resolve install report rows to pkginfo display names and detail-page links. */
export function usePkginfoLinksForInstallReports(
  rows: { item_name: string; item_version: string | null }[],
) {
  const uniqueNames = useMemo(
    () => [...new Set(rows.map((r) => r.item_name).filter(Boolean))].sort(),
    [rows],
  )
  const linkKeys = useMemo(
    () => [
      ...new Set(
        rows.map((r) => installReportLinkKey(r.item_name, r.item_version)),
      ),
    ],
    [rows],
  )

  return useQuery({
    queryKey: ['pkginfo-install-links', uniqueNames.join('\0')],
    queryFn: async () => {
      const byName: Record<string, PkgInfoSummary[]> = {}
      await Promise.all(
        uniqueNames.map(async (name) => {
          const res = await api.get<PaginatedResponse<PkgInfoSummary>>(
            `/pkginfo?name=${encodeURIComponent(name)}&page_size=200`,
          )
          byName[name] = res.items
        }),
      )

      const out: Record<string, PkginfoInstallReportLink> = {}
      for (const key of linkKeys) {
        const sep = key.indexOf('\0')
        const name = sep >= 0 ? key.slice(0, sep) : key
        const version = sep >= 0 ? key.slice(sep + 1) : ''
        const versions = byName[name] ?? []
        const match = version
          ? versions.find((v) => v.version === version)
          : versions[0]
        const displayName =
          match?.display_name?.trim() ||
          versions[0]?.display_name?.trim() ||
          name
        out[key] = {
          displayName,
          pkginfoId: match?.id ?? versions[0]?.id ?? null,
        }
      }
      return out
    },
    enabled: uniqueNames.length > 0,
    staleTime: 5 * 60 * 1000,
  })
}

export interface PkginfoItemMeta {
  displayName: string
  iconName: string | null
}

/** Resolve item keys to pkginfo ``display_name`` and ``icon_name`` (detail fetch per base). */
export function usePkginfoItemMeta(names: string[]) {
  const uniqueRaw = useMemo(
    () => [...new Set(names)].sort(),
    [names.join('\0')],
  )

  const uniqueBases = useMemo(() => {
    const s = new Set<string>()
    for (const raw of uniqueRaw) {
      s.add(parseManifestItemRef(raw).baseName)
    }
    return [...s].sort()
  }, [uniqueRaw.join('\0')])

  return useQuery({
    queryKey: ['pkginfo-item-meta', uniqueRaw.join('\0')],
    queryFn: async () => {
      const byBase: Record<string, PkginfoItemMeta> = {}
      await Promise.all(
        uniqueBases.map(async (base) => {
          try {
            const res = await api.get<PaginatedResponse<PkgInfoSummary>>(
              `/pkginfo?name=${encodeURIComponent(base)}&page_size=1`,
            )
            const pkg = res.items[0]
            if (!pkg) {
              byBase[base] = { displayName: base, iconName: null }
              return
            }
            const d = pkg.display_name?.trim()
            byBase[base] = {
              displayName: d || base,
              iconName: pkg.icon_name?.trim() || null,
            }
          } catch {
            byBase[base] = { displayName: base, iconName: null }
          }
        }),
      )
      const out: Record<string, PkginfoItemMeta> = {}
      for (const raw of uniqueRaw) {
        const { baseName } = parseManifestItemRef(raw)
        out[raw] = byBase[baseName] ?? { displayName: raw, iconName: null }
      }
      return out
    },
    enabled: uniqueRaw.length > 0,
    staleTime: 5 * 60 * 1000,
  })
}
