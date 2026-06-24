import { redirectToLoginForExpiredAuth } from '@/lib/auth-redirect'
import { publicApiBaseUrl } from '@/lib/public-api-base'

const API_BASE = publicApiBaseUrl()

/** Sentinel thrown after a 401 redirect is dispatched. React Query's onError
 * still runs once per failed request; we want the message to be silent in
 * the UI (toasts, error boundaries) because the user is already being sent
 * to /login. The default error UI never sees this — the page is unloading. */
const AUTH_REDIRECT_ERROR = new Error('auth-expired-redirecting')

/** Detect 401, fire the global redirect, and throw a sentinel so callers stop.
 *  Returns true when handled (caller should not continue). */
function handle401(res: Response): boolean {
  if (res.status !== 401) return false
  redirectToLoginForExpiredAuth()
  // Throw so the awaiting caller / React Query short-circuits instead of
  // trying to parse an error body. The page is about to navigate anyway.
  throw AUTH_REDIRECT_ERROR
}

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const token =
    typeof window !== 'undefined' ? localStorage.getItem('token') : null

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options?.headers as Record<string, string>),
  }

  if (token) {
    headers.Authorization = `Bearer ${token}`
  }

  const res = await fetch(`${API_BASE}/api/v1${path}`, {
    ...options,
    headers,
  })

  if (handle401(res)) return undefined as never

  if (!res.ok) {
    const errBody = await res.json().catch(() => ({ detail: res.statusText }))
    const d = errBody.detail
    const msg =
      typeof d === 'string'
        ? d
        : Array.isArray(d)
          ? d
              .map((x: { msg?: string }) => x?.msg)
              .filter(Boolean)
              .join('; ')
          : res.statusText
    if (res.status === 404 && (msg === 'Not Found' || msg === '')) {
      throw new Error(
        'API returned 404 Not Found. If VITE_PUBLIC_API_URL is set, use the API origin only (e.g. http://127.0.0.1:8000), not …/api/v1. Leave it unset to use the same-origin /api proxy.',
      )
    }
    throw new Error(msg || `API error: ${res.status}`)
  }

  if (res.status === 204) return {} as T
  return res.json()
}

/** Plain-text GET (e.g. plist or logs). Reuses the same base URL and auth as ``api``. */
export async function apiGetText(path: string): Promise<string> {
  const token =
    typeof window !== 'undefined' ? localStorage.getItem('token') : null
  const headers: Record<string, string> = {}
  if (token) headers.Authorization = `Bearer ${token}`

  const res = await fetch(`${API_BASE}/api/v1${path}`, { headers })
  if (handle401(res)) return undefined as never
  if (!res.ok) {
    const errBody = await res.json().catch(() => ({ detail: res.statusText }))
    const d = errBody.detail
    const msg =
      typeof d === 'string'
        ? d
        : Array.isArray(d)
          ? d
              .map((x: { msg?: string }) => x?.msg)
              .filter(Boolean)
              .join('; ')
          : res.statusText
    throw new Error(msg || `API error: ${res.status}`)
  }
  return res.text()
}

const api = {
  // Use `<T,>` not `<T>` so generic arrows are not parsed as JSX (Vite/Rolldown, esbuild).
  get: <T>(path: string) => apiFetch<T>(path),
  post: <T>(path: string, body?: unknown) =>
    apiFetch<T>(path, {
      method: 'POST',
      ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
    }),
  put: <T>(path: string, body?: unknown) =>
    apiFetch<T>(path, {
      method: 'PUT',
      ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
    }),
  patch: <T>(path: string, body?: unknown) =>
    apiFetch<T>(path, {
      method: 'PATCH',
      ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
    }),
  delete: <T>(path: string) => apiFetch<T>(path, { method: 'DELETE' }),
}

export { api }

/** Upload a PNG or JPEG as the current user's profile avatar. */
export async function uploadUserAvatar(file: File): Promise<void> {
  const token =
    typeof window !== 'undefined' ? localStorage.getItem('token') : null
  const fd = new FormData()
  fd.append('file', file)
  const headers: Record<string, string> = {}
  if (token) {
    headers.Authorization = `Bearer ${token}`
  }
  const res = await fetch(`${API_BASE}/api/v1/users/me/avatar`, {
    method: 'POST',
    headers,
    body: fd,
  })
  if (handle401(res)) return
  if (!res.ok) {
    const errBody = await res.json().catch(() => ({ detail: res.statusText }))
    const d = errBody.detail
    const msg =
      typeof d === 'string'
        ? d
        : Array.isArray(d)
          ? d
              .map((x: { msg?: string }) => x?.msg)
              .filter(Boolean)
              .join('; ')
          : res.statusText
    throw new Error(msg || `API error: ${res.status}`)
  }
}

export async function deleteUserAvatar(): Promise<void> {
  const token =
    typeof window !== 'undefined' ? localStorage.getItem('token') : null
  const headers: Record<string, string> = {}
  if (token) {
    headers.Authorization = `Bearer ${token}`
  }
  const res = await fetch(`${API_BASE}/api/v1/users/me/avatar`, {
    method: 'DELETE',
    headers,
  })
  if (handle401(res)) return
  if (!res.ok) {
    const errBody = await res.json().catch(() => ({ detail: res.statusText }))
    const d = errBody.detail
    const msg =
      typeof d === 'string'
        ? d
        : Array.isArray(d)
          ? d
              .map((x: { msg?: string }) => x?.msg)
              .filter(Boolean)
              .join('; ')
          : res.statusText
    throw new Error(msg || `API error: ${res.status}`)
  }
}

export interface IconUploadResult {
  icon_name: string
  filename: string
}

/** Upload a PNG into the software_icon table (served at /icons/&lt;name&gt;.png and /repo/icons/&lt;name&gt;.png). */
export async function uploadSoftwareIcon(
  file: File,
  iconName: string,
): Promise<IconUploadResult> {
  const token =
    typeof window !== 'undefined' ? localStorage.getItem('token') : null
  const fd = new FormData()
  fd.append('file', file)
  fd.append('icon_name', iconName)
  const headers: Record<string, string> = {}
  if (token) {
    headers.Authorization = `Bearer ${token}`
  }
  const res = await fetch(`${API_BASE}/api/v1/icons/upload`, {
    method: 'POST',
    headers,
    body: fd,
  })
  if (handle401(res)) return undefined as never
  if (!res.ok) {
    const errBody = await res.json().catch(() => ({ detail: res.statusText }))
    const d = errBody.detail
    const msg =
      typeof d === 'string'
        ? d
        : Array.isArray(d)
          ? d
              .map((x: { msg?: string }) => x?.msg)
              .filter(Boolean)
              .join('; ')
          : res.statusText
    throw new Error(msg || `API error: ${res.status}`)
  }
  return res.json()
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface PkgInfoBulkUpdateRequest {
  pkginfo_ids: string[]
  category?: string | null
  catalog_names?: string[]
}

export interface PkgInfoBulkUpdateResult {
  updated: number
}

export interface PkgInfoSummary {
  id: string
  name: string
  display_name: string | null
  icon_name: string | null
  version: string
  category: string | null
  developer: string | null
  catalog_names: string[]
  unattended_install: boolean
  unattended_uninstall: boolean
  minimum_os_version: string | null
  installer_type: string | null
  restart_action: string | null
  pending_metadata?: boolean
  is_latest?: boolean
  deployment_status?: DeploymentStatus
  shard_percent?: number | null
  is_first_production_deploy?: boolean
  in_manifest?: boolean
  install_count?: number
  failed_install_count?: number
  created_at: string
  updated_at: string
}

export type DeploymentStatus =
  | 'not_in_production'
  | 'pending_rollout'
  | 'sharding'
  | 'fully_deployed'
  | 'paused'

export interface PkgInfoShardQueueItemRead {
  id: string
  name: string
  version: string
  display_name: string | null
  deployment_status: DeploymentStatus
  shard_rollout_status: string
  shard_percent: number | null
  is_first_production_deploy: boolean
  in_manifest: boolean
}

export interface PkgInfoShardStatusRead {
  active: boolean
  summary: string
  deployment_status: DeploymentStatus
  shard_rollout_status: string
  shard_percent: number | null
  shard_percent_override: number | null
  scheduled_shard_percent: number | null
  shard_started_at: string | null
  rollout_days: number
  current_day: number | null
  is_first_production_deploy: boolean
  in_manifest: boolean
  manifest_names: string[]
  manifest_warning: boolean
  installable_condition: string | null
  production_shard_enabled: boolean
  net_new_shard_policy: string
}

export interface PkgInfoDetail extends PkgInfoSummary {
  description: string | null
  icon_name: string | null
  installer_item_location: string | null
  installer_item_hash: string | null
  installer_item_size: number | null
  installed_size: number | null
  installer_type: string | null
  minimum_os_version: string | null
  maximum_os_version: string | null
  uninstall_method: string | null
  unattended_uninstall: boolean
  autoremove: boolean
  uninstallable: boolean
  installs: InstallItem[] | null
  receipts: ReceiptItem[] | null
  blocking_applications: string[] | null
  items_to_copy: ItemToCopy[] | null
  supported_architectures: string[] | null
  requires: string[] | null
  update_for: string[] | null
  preinstall_script: string | null
  postinstall_script: string | null
  preuninstall_script: string | null
  postuninstall_script: string | null
  installcheck_script: string | null
  uninstallcheck_script: string | null
  version_script: string | null
  notes: string | null
  restart_action: string | null
  on_demand: boolean
  force_install_after_date: string | null
  apple_item: boolean
  installable_condition: string | null
  package_path: string | null
  package_complete_url: string | null
  minimum_munki_version: string | null
  uninstaller_item_location: string | null
  is_deleted: boolean
  auto_promote: boolean
  promotion_channel_id: string | null
  pending_metadata?: boolean
}

export interface SoftwareUploadFields {
  display_name: string
  name?: string
  catalogs?: string
  category?: string
  developer?: string
  description?: string
  unattended_install?: boolean
  /**
   * Path under ``pkgs/`` where the binary will live (e.g. ``apps/Slack``).
   * When empty/omitted the file lands at the root of ``pkgs/``. A leading
   * ``pkgs/`` in the value is tolerated server-side.
   */
  munki_repo_subdir?: string
}

/**
 * Stream a pkg or dmg to ``POST /api/v1/munki/upload``. Uses XHR (not fetch)
 * so we can wire ``onProgress`` to the network upload — fetch streaming on
 * upload bodies is still inconsistent across browsers in 2026.
 */
export function uploadSoftwareFile(
  file: File,
  fields: SoftwareUploadFields,
  onProgress?: (loaded: number, total: number) => void,
): Promise<PkgInfoDetail> {
  const token =
    typeof window !== 'undefined' ? localStorage.getItem('token') : null

  const fd = new FormData()
  fd.append('file', file)
  fd.append('display_name', fields.display_name)
  if (fields.name) fd.append('name', fields.name)
  fd.append('catalogs', fields.catalogs ?? 'testing')
  if (fields.category) fd.append('category', fields.category)
  if (fields.developer) fd.append('developer', fields.developer)
  if (fields.description) fd.append('description', fields.description)
  if (fields.unattended_install)
    fd.append('unattended_install', String(fields.unattended_install))
  if (fields.munki_repo_subdir)
    fd.append('munki_repo_subdir', fields.munki_repo_subdir)

  return new Promise<PkgInfoDetail>((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${API_BASE}/api/v1/munki/upload`)
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`)
    xhr.upload.onprogress = (evt) => {
      if (evt.lengthComputable && onProgress) {
        onProgress(evt.loaded, evt.total)
      }
    }
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText) as PkgInfoDetail)
        } catch (e) {
          reject(e)
        }
        return
      }
      // 401 mid-upload (long uploads can outlive the JWT). Bounce to /login
      // instead of surfacing a confusing "Upload failed: 401 Unauthorized".
      if (xhr.status === 401) {
        redirectToLoginForExpiredAuth()
        reject(AUTH_REDIRECT_ERROR)
        return
      }
      let msg = `Upload failed: ${xhr.status} ${xhr.statusText}`
      try {
        const body = JSON.parse(xhr.responseText)
        const d = body?.detail
        if (typeof d === 'string') msg = d
      } catch {
        // keep default msg
      }
      reject(new Error(msg))
    }
    xhr.onerror = () => reject(new Error('Network error during upload'))
    xhr.send(fd)
  })
}

export interface InstallItem {
  type?: string
  path?: string
  CFBundleIdentifier?: string
  CFBundleName?: string
  CFBundleShortVersionString?: string
  CFBundleVersion?: string
  minosversion?: string
  version_comparison_key?: string
  [key: string]: unknown
}

export interface ReceiptItem {
  packageid?: string
  version?: string
  installed_size?: number
  optional?: boolean
  [key: string]: unknown
}

export interface ItemToCopy {
  source_item?: string
  destination_path?: string
  destination_item?: string
  user?: string
  group?: string
  mode?: string
  [key: string]: unknown
}

export interface CatalogRead {
  id: string
  name: string
  display_name: string | null
  description: string | null
  is_production: boolean
  is_quarantine: boolean
  sort_order: number
  created_at: string
  item_count: number
}

export interface PromotionChannelStepRead {
  id: string
  step_order: number
  source_catalog_id: string
  target_catalog_id: string
  dwell_days: number
  requires_manual_approval: boolean
}

export interface PromotionChannelRead {
  id: string
  name: string
  description: string | null
  created_at: string
  updated_at: string
  steps: PromotionChannelStepRead[]
}

export interface WorkflowPreferencesRead {
  default_promotion_channel_id: string | null
  production_shard_days: number
  production_shard_enabled: boolean
  net_new_shard_policy: string
}

/** Matches backend `ConditionalItemBlock` (Munki conditional_items array entries). */
export type ConditionalItemBlock = {
  condition: string
  managed_installs?: string[]
  managed_uninstalls?: string[]
  managed_updates?: string[]
  optional_installs?: string[]
  featured_items?: string[]
  default_installs?: string[]
  included_manifests?: string[]
  conditional_items?: ConditionalItemBlock[]
}

export interface ManifestRead {
  id: string
  name: string
  display_name: string | null
  notes: string | null
  conditional_items: ConditionalItemBlock[] | null
  catalog_names: string[]
  managed_installs: string[]
  managed_uninstalls: string[]
  managed_updates: string[]
  optional_installs: string[]
  featured_items: string[]
  default_installs: string[]
  included_manifest_names: string[]
  created_at: string
  updated_at: string
}

export interface AutoPkgRunRead {
  id: string
  status: string
  trigger_type: string
  triggered_by: string | null
  /** github = GitHub Actions; local = run script on your Mac */
  runner_type: string
  github_run_id: string | null
  github_run_url: string | null
  recipe_filter: string[] | null
  total_recipes: number | null
  recipes_succeeded: number | null
  recipes_failed: number | null
  recipes_imported: number | null
  error_message: string | null
  started_at: string | null
  completed_at: string | null
  created_at: string
  results: RunResultRead[]
  schedule_id: string | null
  schedule_name: string | null
}

export interface AutoPkgScheduleRead {
  id: string
  name: string
  cron_expression: string
  timezone: string
  recipe_names: string[] | null
  runner_type: string
  enabled: boolean
  last_run_at: string | null
  next_run_at: string | null
  created_at: string
  updated_at: string
}

export interface RunResultRead {
  id: string
  recipe_identifier: string
  recipe_name: string
  status: string
  imported_version: string | null
  imported_display_name: string | null
  imported_pkg_path: string | null
  imported_pkginfo_path: string | null
  imported_catalogs: string[] | null
  virustotal_results: unknown
  trust_info_diff: unknown
  approval_status: string
  approved_by: string | null
  approved_at: string | null
  approval_comment: string | null
  log_output: string | null
  error_message: string | null
  duration_seconds: number | null
  created_at: string
}

export interface PkgInfoCatalogMembershipRead {
  catalog_name: string
  entered_at: string
}

export interface PkgInfoPromotionLegRead {
  step_order: number
  source_catalog_name: string
  target_catalog_name: string
  dwell_days: number
  promote_at: string
  days_remaining: number
  status: string
  dwell_clock_start_at: string
}

export interface PkgInfoPromotionStatusRead {
  active: boolean
  summary: string | null
  auto_promote: boolean
  promotion_channel_id: string | null
  channel_name: string | null
  current_catalog_summary: string
  catalog_memberships: PkgInfoCatalogMembershipRead[]
  legs: PkgInfoPromotionLegRead[]
}

export interface PkgInfoPromotionQueueItemRead {
  id: string
  name: string
  version: string
  display_name: string | null
  channel_name: string
  next_source_catalog: string
  next_target_catalog: string
  leg_status: string
  days_remaining: number
  promote_at: string
}

export interface AutoPkgRecipeRead {
  id: string
  identifier: string
  name: string
  parent_recipe: string | null
  source_repo_full_name: string | null
  is_enabled: boolean
  /** When true, runner plist sets MunkiImporter ``Input.extract_icon`` */
  extract_icon_enabled?: boolean
  auto_promote: boolean
  promotion_channel_id: string | null
  override_data: unknown
  trust_info: unknown
  input_variables: unknown
  trust_status: string
  trust_verified_at: string | null
  trust_approved_by: string | null
  trust_approved_at: string | null
  last_run_at: string | null
  last_run_status: string | null
  created_at: string
  updated_at: string
  /** Resolved server-side from PkgInfo (Input.NAME / recipe name). Omitted on older APIs. */
  pkginfo_display_name?: string | null
  pkginfo_icon_name?: string | null
}

export interface TrustChangeRequestRead {
  id: string
  recipe_id: string
  old_trust_info: unknown
  new_trust_info: unknown
  diff: unknown
  status: string
  requested_at: string
  reviewed_by: string | null
  reviewed_at: string | null
  comment: string | null
}

/** ``GET /autopkg/trust-changes/pending-count`` */
export interface TrustPendingCountResponse {
  count: number
}

/** ``GET /autopkg/recipes/trust-summary`` */
export interface RecipeTrustSummaryResponse {
  verified: number
  failed: number
  pending_approval: number
  unknown: number
}

export interface TrustCommitResolveResponse {
  commit_sha: string | null
  commit_url: string | null
}

export interface CachedGitHubRecipe {
  id: string
  repo_id: string
  name: string
  filename: string
  path: string
  identifier_guess: string
  url: string
}

export interface CachedGitHubRepo {
  id: string
  full_name: string
  name: string
  html_url: string
  clone_url: string | null
  description: string | null
  stars: number
  updated_at: string | null
  default_branch: string | null
  synced_at: string
  /** When true, repo is not dropped by “Sync Repos” (autopkg org list). */
  is_custom: boolean
  cached_recipes: CachedGitHubRecipe[]
}

export interface DiscoveredRecipe {
  name: string
  filename: string
  path: string
  identifier_guess: string
  repo_full_name: string
  url: string
}

export interface SearchedRecipe {
  name: string
  filename: string
  path: string
  identifier_guess: string
  repo_full_name: string
  repo_name: string
  repo_url: string
  url: string
}

export interface AuditLogRead {
  id: string
  user_id: string | null
  user_email: string | null
  action: string
  entity_type: string
  entity_id: string
  entity_name: string | null
  before_snapshot: unknown
  after_snapshot: unknown
  changes: unknown
  ip_address: string | null
  notes: string | null
  created_at: string
}

export interface UiSettingsRead {
  github_repo: string
  /** Server default when the trigger dialog does not override */
  autopkg_runner_mode: string
}

/** GET/PATCH /settings/munki-repo-basic-auth — JWT + admin.settings */
export interface MunkiRepoBasicAuthRead {
  enabled: boolean
  username: string
  env_override_active: boolean
}

export interface MunkiRepoBasicAuthPatchBody {
  enabled: boolean
  username?: string
  password?: string | null
}

export interface MunkiRepoBasicAuthPatchResponse {
  enabled: boolean
  username: string
  env_override_active: boolean
  /** Present once after setting a new password */
  client_authorization_header?: string | null
}

/**
 * GET/PATCH /settings/munki-repo-urls — external `PackageURL` /
 * `ClientResourceURL` written into enrolled clients' `.mobileconfig`.
 *
 * These replace the old 302-redirect approach for `/repo/pkgs/*` and
 * `/repo/client_resources/*`. Clients fetch those assets direct from these
 * URLs, so `Authorization` headers aren't dropped on cross-origin redirects.
 */
export interface MunkiRepoUrlsRead {
  package_url: string
  client_resource_url: string
  package_url_env_override: boolean
  client_resource_url_env_override: boolean
  /** True when `client_resource_url` was derived from `package_url` because
   * neither env nor DB explicitly set it. */
  client_resource_url_derived: boolean
}

export interface MunkiRepoUrlsPatchBody {
  /** Omit to leave unchanged. Empty string clears. */
  package_url?: string | null
  /** Omit to leave unchanged. Empty string clears (re-enables derivation). */
  client_resource_url?: string | null
}

export interface ClientMachineSummary {
  id: string
  serial_number: string
  hostname: string | null
  os_version: string | null
  machine_model: string | null
  munki_version: string | null
  manifest_name: string | null
  last_checkin_at: string | null
  disk_free_gb: number | null
  install_report_count: number
}

export interface CheckinHistoryPoint {
  date: string
  count: number
}

/** GET /pkginfo/{id}/install-reports/summary */
export interface PkgInfoInstallReportSummary {
  item_name: string
  total_reports: number
  unique_machines: number
  by_status: Record<string, number>
  days: number
  versions: string[]
  timeline_by_version: Record<string, CheckinHistoryPoint[]>
  timeline: CheckinHistoryPoint[]
}

export interface ClientInstallReportRow {
  id: string
  item_name: string
  item_version: string | null
  status: string
  error_message: string | null
  /** Munki-derived: managed_install, optional_install, managed_update, apple_software_update, removal, … */
  install_reason: string | null
  install_date: string | null
  created_at: string
}

/** Flat list row from GET /reports/installs (includes machine). */
export interface ClientInstallReportListItem extends ClientInstallReportRow {
  machine_id: string
  hostname: string | null
  serial_number: string | null
}

export interface ClientMachineDetail {
  id: string
  serial_number: string
  hostname: string | null
  /** Marketing name from Munki MachineInfo when agent sends it (e.g. MacBook Pro). */
  product_name?: string | null
  /** Apple FMIP-style PNG (same CDN as MunkiReport). */
  device_image_url?: string | null
  platform_uuid?: string | null
  os_version: string | null
  os_build: string | null
  machine_model: string | null
  cpu_type: string | null
  cpu_arch?: string | null
  physical_cpus?: number | null
  logical_cpus?: number | null
  ram_mb: number | null
  disk_size_gb: number | null
  disk_free_gb: number | null
  munki_version: string | null
  manifest_name: string | null
  client_identifier: string | null
  hardware_info: unknown
  installed_software: unknown
  last_checkin_at: string | null
  first_checkin_at: string | null
  /** All-time count of POST /reports/checkin for this machine. */
  checkin_total?: number
  /** Daily buckets for the last ~90 days (including zeros). */
  checkin_history?: CheckinHistoryPoint[]
  install_reports: ClientInstallReportRow[]
}

export interface FleetComplianceOverview {
  total_machines: number
  checked_in_last_7_days: number
  stale_over_30_days: number
  compliance_percentage: number
}

/** GET /reports/fleet-activity */
export interface FleetActivityTimeseries {
  days: number
  checkins_by_day: CheckinHistoryPoint[]
  install_rows_by_day: CheckinHistoryPoint[]
}

// ---------------------------------------------------------------------------
// Client enrollment (Mac onboarding)
// ---------------------------------------------------------------------------

/** POST /enroll/tokens — admin body. */
export interface EnrollmentTokenCreateBody {
  label?: string | null
  manifest_name?: string | null
  ttl_hours?: number | null
  /**
   * Repo Basic auth password, required when Basic auth is enabled via the
   * Settings UI (DB-stored Argon2 hash). Ignored in env-mode and when auth
   * is off. Server verifies against the hash before accepting.
   */
  repo_password?: string | null
}

/** POST /enroll/tokens response. Plaintext token is returned ONCE. */
export interface EnrollmentTokenCreated {
  id: string
  token: string
  label: string | null
  manifest_name: string | null
  expires_at: string | null
  created_at: string
  enroll_url: string
  embeds_basic_auth: boolean
}

/** GET /enroll/tokens item. */
export interface EnrollmentTokenRow {
  id: string
  label: string | null
  manifest_name: string | null
  expires_at: string | null
  redeemed_at: string | null
  created_at: string
}

/** GET /enroll/status — public server advert for the walkthrough page. */
export interface EnrollmentStatus {
  server_base_url: string
  repo_basic_auth_enabled: boolean
  profile_embeds_basic_auth: boolean
}

/**
 * Redeem a token and download the `.mobileconfig`. Returns the Blob so the
 * caller can trigger a file download in the browser.
 */
export async function redeemEnrollmentProfile(
  token: string,
  manifestName?: string | null,
): Promise<Blob> {
  const body: { token: string; manifest_name?: string } = { token }
  if (manifestName?.trim()) {
    body.manifest_name = manifestName.trim()
  }
  const res = await fetch(`${API_BASE}/api/v1/enroll/profile`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const errBody = await res.json().catch(() => ({ detail: res.statusText }))
    const d = errBody.detail
    const msg =
      typeof d === 'string' ? d : res.statusText || `HTTP ${res.status}`
    throw new Error(msg)
  }
  return res.blob()
}

export interface InsightsHistoryMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface InsightsQueryRequest {
  question: string
  history?: InsightsHistoryMessage[]
}

export interface InsightsToolUsed {
  name: string
  args: Record<string, unknown>
  summary: string
}

export interface InsightsTableData {
  columns: string[]
  rows: (string | number | null)[][]
}

export interface InsightsQueryResponse {
  answer: string
  tools_used: InsightsToolUsed[]
  data?: InsightsTableData | null
}
