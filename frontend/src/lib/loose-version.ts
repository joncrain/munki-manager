/**
 * Munki-compatible loose version comparison (Python distutils.version.LooseVersion).
 * @see https://managingosx.wordpress.com/2020/10/06/this-one-goes-to-11-macos-version-comparisons-and-munki/
 */

const COMPONENT_RE = /(\d+|[a-z]+|\.)/gi

export type LooseVersionPart = number | string

export function parseLooseVersion(
  vstring: string | null | undefined,
): LooseVersionPart[] {
  if (!vstring) return []
  const components: LooseVersionPart[] = []
  for (const match of vstring.matchAll(COMPONENT_RE)) {
    const part = match[0]
    if (!part || part === '.') continue
    const asNumber = Number(part)
    components.push(Number.isNaN(asNumber) ? part : asNumber)
  }
  return components
}

function compareLooseParts(
  left: LooseVersionPart[],
  right: LooseVersionPart[],
): number {
  const max = Math.max(left.length, right.length)
  for (let i = 0; i < max; i += 1) {
    const l = left[i]
    const r = right[i]
    if (l === undefined) return r === undefined ? 0 : -1
    if (r === undefined) return 1
    if (l === r) continue
    if (typeof l === 'number' && typeof r === 'number') {
      return l < r ? -1 : 1
    }
    const ls = String(l)
    const rs = String(r)
    if (ls < rs) return -1
    if (ls > rs) return 1
  }
  return 0
}

/** Return -1, 0, or 1 for two version strings. */
export function compareLooseVersions(
  left: string | null | undefined,
  right: string | null | undefined,
): number {
  return compareLooseParts(parseLooseVersion(left), parseLooseVersion(right))
}

export function sortByLooseVersion<T>(
  items: T[],
  getVersion: (item: T) => string | null | undefined,
  order: 'asc' | 'desc' = 'desc',
): T[] {
  const sorted = [...items].sort((a, b) =>
    compareLooseVersions(getVersion(a), getVersion(b)),
  )
  return order === 'desc' ? sorted.reverse() : sorted
}

/** TanStack Table sortingFn for version columns. */
export function looseVersionSortingFn<T>(
  rowA: { getValue: (columnId: string) => unknown },
  rowB: { getValue: (columnId: string) => unknown },
  columnId: string,
): number {
  return compareLooseVersions(
    rowA.getValue(columnId) as string | null | undefined,
    rowB.getValue(columnId) as string | null | undefined,
  )
}
