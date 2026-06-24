/**
 * Client-side preview of how the backend will derive ``PkgInfo.name`` when
 * the user leaves the "Name" field blank in the upload dialog.
 *
 * This must stay in sync with ``automunki.services.munki_import._derive_name``
 * — the preview is purely cosmetic, but if it lies the user gets a different
 * ``name`` than the dialog promised, which is the worst kind of footgun for
 * a field that downstream Munki manifest items reference verbatim.
 */

const INSTALLER_EXT = /\.(pkg|mpkg|dmg|zip)$/i
// Match the backend's ``_VERSION_TAIL_RE``: ``-`` *or* ``_`` followed by a
// digit (because ``_slug`` turns whitespace into underscore, so
// ``"Slack 4.36"`` → ``"Slack_4.36"`` and we still want to strip ``_4.36``).
const VERSION_TAIL = /[-_]\d[\w.-]*$/

function slug(input: string): string {
  // Match Python's ``re.sub(r"[^\w.\-]+", "_", ..., flags=re.UNICODE)`` plus
  // the surrounding ``strip("._-")``. ``\w`` here is the Unicode word class
  // (letters/digits/underscore in any script) — JS's ``u``-flag ``\w`` is
  // ASCII-only, so we approximate by using a character class that matches
  // anything that isn't a word char, dot, or hyphen.
  const cleaned = input
    .trim()
    .replace(/[^\p{L}\p{N}_.-]+/gu, '_')
    .replace(/^[._-]+|[._-]+$/g, '')
  return cleaned || 'uploaded'
}

function stripInstallerExtension(filename: string): string {
  return filename.replace(INSTALLER_EXT, '')
}

export function deriveAutoName(opts: {
  displayName: string
  filename?: string | null
}): string {
  const display = opts.displayName.trim()
  const source = display
    ? display
    : opts.filename
      ? stripInstallerExtension(opts.filename)
      : ''
  const base = slug(source)
  // The frontend doesn't know the xar-parsed version yet (the binary hasn't
  // hit the backend), so we only run the heuristic ``-<digit>...`` strip
  // here. The backend will additionally do an exact-version-suffix strip if
  // parsing succeeds, which is a strict subset of what the heuristic catches.
  const trimmed = base.replace(VERSION_TAIL, '').replace(/[._-]+$/, '')
  return trimmed || base
}
