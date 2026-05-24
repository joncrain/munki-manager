/**
 * Munki manifest item refs: ``name``, ``name-version``, or ``name--version``
 * when the version is ambiguous (e.g. ``baseName`` itself contains a dash, or
 * the version string contains a dash). See
 * https://github.com/munki/munki/wiki/Manifests#item-names.
 *
 * The split logic here MUST match Munki's own ``nameAndVersion`` on the
 * client. If our UI labels an item ``baseName="foo"`` but the client resolves
 * it as ``"foo-bar"``, admins get told the item exists when in fact it can
 * never install — exactly the foot-gun this module exists to prevent.
 */
export function parseManifestItemRef(raw: string): {
  baseName: string
  version: string | null
} {
  // Explicit ``--`` separator wins (the Munki convention for disambiguating
  // names that contain dashes followed by digits).
  const double = raw.indexOf('--')
  if (double !== -1) {
    const baseName = raw.slice(0, double)
    const version = raw.slice(double + 2).trim() || null
    return { baseName, version }
  }
  // Otherwise split on the first dash that is immediately followed by a
  // digit — Munki's client-side rule.
  for (let i = 0; i < raw.length; i += 1) {
    if (raw[i] === '-' && i + 1 < raw.length && /\d/.test(raw[i + 1])) {
      const version = raw.slice(i + 1).trim() || null
      return { baseName: raw.slice(0, i), version }
    }
  }
  return { baseName: raw, version: null }
}

export function formatManifestItemRef(
  baseName: string,
  version: string | null | undefined,
): string {
  const v = version?.trim()
  if (!v) return baseName
  // Prefer the explicit ``--`` form whenever single-dash would be ambiguous:
  //   * the version itself contains a dash (Munki would split early), or
  //   * the baseName already contains a ``-<digit>`` sequence (Munki would
  //     stop at that earlier dash and grab the wrong version).
  // Otherwise stay on the compact ``-`` form, which is what the Munki wiki
  // and most pkginfo writers use.
  const ambiguous = v.includes('-') || /-\d/.test(baseName)
  if (ambiguous) return `${baseName}--${v}`
  return `${baseName}-${v}`
}

export function manifestItemBaseNamesInUse(items: string[]): Set<string> {
  return new Set(items.map((raw) => parseManifestItemRef(raw).baseName))
}
