# Munki Manager API Reference

Base URL: `/api/v1`

Full interactive documentation is available at `/api/docs` (Swagger UI) when the server is running.

## Authentication

Most endpoints require a Bearer JWT.

For how to create accounts, configure `AUTH_MODE` / `AUTH_REGISTRATION_OPEN`, and bootstrap the first admin, see **[users-and-auth.md](users-and-auth.md)**.

```
Authorization: Bearer <jwt_token>
```

The **local AutoPkg daemon** (`poll_local_autopkg.sh`) may instead use a shared secret configured on the server as **`LOCAL_RUNNER_TOKEN`**: send `Authorization: Bearer <same value>` for `POST /autopkg/runs/claim-next-local`, `GET`/`PUT /autopkg/metadata-cache`, `GET /autopkg/runs/config`, `GET /autopkg/runs/{run_id}` (read the run row for `recipe_filter`), `POST /autopkg/pkginfo/ingest`, and `POST /autopkg/icons/ingest` (see [`docs/local-autopkg-runner.md`](local-autopkg-runner.md)). Those ingest routes are also callable **without** a token on a trusted network (same as before).

### Auth Endpoints

`/auth/login`, `/auth/register`, `/auth/logout`, and `/users/me` are mounted by FastAPI Users; full schemas are in Swagger at `/api/docs`.

| Method | Path | Description |
|--------|------|-------------|
| POST | `/auth/login` | Login with email/password, returns JWT (OAuth2 password flow) |
| POST | `/auth/logout` | Logout (invalidate JWT cookie/header) |
| POST | `/auth/register` | Register a new user. Returns **403** when `AUTH_REGISTRATION_OPEN=false`. |
| GET | `/auth/config` | Public; returns `{ auth_mode, registration_open, oidc_enabled, ... }` so the SPA can adapt at runtime. |
| GET | `/auth/me` | Compatibility wrapper around the FastAPI Users `/users/me` with extra Munki Manager fields (page write/read sets, `is_superuser`, `role`, avatar URL). |
| GET | `/users/me` | FastAPI Users profile. |
| PATCH | `/users/me` | Update current user profile. |
| POST | `/users/me/avatar` | Multipart `file` (PNG/JPEG, ≤ 1 MB); bytes stored in `user.avatar_data` (Postgres bytea). |
| GET | `/users/me/avatar` | Serve the current user's avatar (JWT required). |
| DELETE | `/users/me/avatar` | Remove the current user's avatar. |

### OIDC (when `AUTH_MODE=oidc`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/auth/oidc/authorize` | Redirect to the configured IdP authorization endpoint with PKCE. |
| GET | `/auth/oidc/callback` | IdP callback; exchanges the code, upserts the user, sets a Munki Manager JWT cookie, and redirects to `PUBLIC_APP_URL`. |

### RBAC (admin only — requires `admin.access`)

| Method | Path | Description |
|--------|------|-------------|
| GET / POST | `/rbac/roles` | List or create roles. |
| PATCH / DELETE | `/rbac/roles/{role_id}` | Rename or delete a role. |
| PUT | `/rbac/roles/{role_id}/permissions` | Replace the role's `(page_key, can_write)` set. |
| GET | `/rbac/users` | List users with their assigned roles. |
| PUT | `/rbac/users/{user_id}/roles` | Replace a user's role memberships. |
| DELETE | `/rbac/users/{user_id}` | Hard-delete a user (removes role memberships first). |

### Client enrollment

| Method | Path | Description |
|--------|------|-------------|
| GET / POST | `/enroll/tokens` | Admin: list or create one-time enrollment tokens (returns plaintext once on create). |
| DELETE | `/enroll/tokens/{token_id}` | Revoke a token. |
| GET | `/enroll/status?token=...` | Public: report whether a token is valid/redeemed/expired (used by the public `/enroll` page). |
| POST | `/enroll/profile` | Public: redeem a token and download the generated `.mobileconfig` (consumes the token). |

See [`client-onboarding.md`](client-onboarding.md) for the end-to-end flow.

## Settings (UI)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/settings/ui` | Read-only UI config (`github_repo`, default `autopkg_runner_mode`) |
| GET / PATCH | `/settings/munki-repo-basic-auth` | HTTP Basic credentials guarding `/repo/*` (singleton; admin-gated). |
| GET / PATCH | `/settings/munki-repo-urls` | External `PackageURL` / `ClientResourceURL` written into enrolled clients' `.mobileconfig`. `PATCH` returns 409 when the corresponding env var pins the field. |

## PkgInfo (Software)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/pkginfo` | List/search software (paginated) |
| POST | `/munki/upload` | **Direct software upload.** Multipart: `file` (`.pkg` / `.dmg`), `display_name` (required), `name`, `catalogs` (comma-separated, default `testing`), `category`, `developer`, `description`, `unattended_install`. Hashes the file, optionally extracts version + receipts from a flat-pkg xar TOC, streams bytes to the configured `STORAGE_BACKEND`, and creates a `PkgInfo` row. Returns 503 when `STORAGE_BACKEND=none`. RBAC: `munki.software` (write). |
| GET | `/pkginfo/categories` | Distinct category strings used by any pkginfo |
| GET | `/pkginfo/promotion-queue` | Items waiting on a promotion-channel dwell timer |
| POST | `/pkginfo/bulk-update` | Apply a single update (catalogs, category, etc.) to many pkginfo rows |
| GET | `/pkginfo/{id}` | Get software detail |
| GET | `/pkginfo/{id}/plist` | Get compiled plist XML |
| GET | `/pkginfo/{id}/promotion-status` | Current channel + step + dwell remaining for this pkginfo |
| GET | `/pkginfo/{id}/install-reports/summary` | Install-report stats + 90-day timeline for this item name |
| PUT | `/pkginfo/{id}` | Update software metadata |
| PUT | `/pkginfo/{id}/catalogs` | Replace this pkginfo's catalog set |
| DELETE | `/pkginfo/{id}` | Soft-delete software |
| POST | `/pkginfo/{id}/promote` | Promote to a catalog (manual override of channel timing) |

## UI icons (PNG)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/icons/upload` | Multipart: `file` (PNG), optional form `icon_name` (stem without `.png`). Upserts into the `software_icon` table. |
| GET | `/icons/{basename}` | Serve `{basename}.png` from the `software_icon` table with SHA-256 `ETag` / `If-None-Match` support. Same table is served at `/repo/icons/{basename}.png` for Munki clients. |

### Query Parameters for GET /pkginfo

| Param | Type | Description |
|-------|------|-------------|
| page | int | Page number (default: 1) |
| page_size | int | Items per page (default: 50, max: 200) |
| search | string | Search name/display_name |
| catalog | string | Filter by catalog name |
| category | string | Filter by category |
| name | string | Filter by exact name |
| sort_by | string | Sort field (default: name) |
| sort_order | string | asc or desc |

## Catalogs

| Method | Path | Description |
|--------|------|-------------|
| GET | `/catalogs` | List all catalogs with item counts |
| POST | `/catalogs` | Create a new catalog |
| PUT | `/catalogs/{id}` | Update catalog (name, `is_production`, `is_quarantine`) |
| DELETE | `/catalogs/{id}` | Delete an empty catalog |
| GET | `/catalogs/{id}/items` | List items in a catalog |
| POST | `/catalogs/{id}/compile` | Generate catalog plist XML |
| POST | `/catalogs/makecatalogs` | Verify all catalogs (compile each, return sizes + warnings) |

## Promotion channels

| Method | Path | Description |
|--------|------|-------------|
| GET / POST | `/promotion-channels` | List or create promotion channels (e.g. `slow`, `fast`). |
| GET / PATCH / DELETE | `/promotion-channels/{id}` | Manage a single channel and its ordered steps. |

The global default channel is set via `/workflow` (`default_promotion_channel_id` on `app_workflow_preferences`).

## Workflow preferences

| Method | Path | Description |
|--------|------|-------------|
| GET | `/workflow` | Read singleton workflow preferences (default promotion channel, etc.). |
| PATCH | `/workflow` | Update workflow preferences. |

## Manifests

| Method | Path | Description |
|--------|------|-------------|
| GET | `/manifests` | List all manifests |
| GET | `/manifests/{id}` | Get manifest detail |
| GET | `/manifests/{id}/compile` | Generate manifest plist XML |
| POST | `/manifests` | Create a new manifest |
| PUT | `/manifests/{id}` | Update manifest |
| DELETE | `/manifests/{id}` | Delete manifest |

## AutoPkg

| Method | Path | Description |
|--------|------|-------------|
| POST | `/autopkg/runs` | Trigger a new AutoPkg run (body: `recipe_names`, optional `runner`: `github` \| `local`; default from `AUTOPKG_RUNNER_MODE`) |
| GET | `/autopkg/runs` | List run history (paginated) |
| POST | `/autopkg/runs/claim-next-local` | Atomically claim the oldest pending **local** run (`status` → `running`). **204** if none. JWT (AutoPkg runs write) or `LOCAL_RUNNER_TOKEN` |
| GET | `/autopkg/runs/{id}` | Get run detail with results |
| POST | `/autopkg/runs/{id}/results` | Post per-recipe result (webhook) |
| POST | `/autopkg/runs/{id}/pkgs` | **Streaming pkg/dmg upload from a runner.** Multipart: `file`, `recipe_identifier`, optional `relative_path`. Streams bytes to `STORAGE_BACKEND` and returns the public URL; the runner then attaches it as `imported_pkg_url` on the result. Returns 503 when `STORAGE_BACKEND=none` so old deployments keep working. Auth: `LOCAL_RUNNER_TOKEN` |
| POST | `/autopkg/runs/{id}/complete` | Mark run as complete (webhook) |
| POST | `/autopkg/pkginfo/ingest` | Ingest a pkginfo dict from a runner (body JSON). Unauthenticated on **trusted** networks; otherwise JWT or `LOCAL_RUNNER_TOKEN` |
| POST | `/autopkg/icons/ingest` | Multipart: runner-extracted PNG for `software_icon` (`file`, optional `icon_name`). Same auth model as `pkginfo/ingest` |
| GET | `/autopkg/metadata-cache` | cloud-autopkg-runner cache blob (per-recipe keys → entries) |
| PUT | `/autopkg/metadata-cache` | Replace entire cache from runner (`cache_data` JSON) |
| DELETE | `/autopkg/metadata-cache` | Clear cache; optional query `recipe_key` (e.g. `AdobeReader.munki.recipe`) deletes one entry |
| GET | `/autopkg/recipes` | List managed recipes |
| POST | `/autopkg/recipes` | Create/add a recipe |
| POST | `/autopkg/recipes/import-override` | Import an existing AutoPkg override plist (XML, base64 binary plist, YAML, or JSON) into `autopkg_recipe` |
| PUT | `/autopkg/recipes/{id}` | Update recipe config |
| GET | `/autopkg/recipes/discover` | List cached GitHub recipe repos (Discover UI) |
| POST | `/autopkg/cache/sync-repos` | Refresh repo list from the autopkg GitHub org |
| POST | `/autopkg/cache/sync-recipes` | Index `.munki.recipe` files for all cached repos |
| POST | `/autopkg/cache/sync-repo/{owner}/{name}` | Index recipes for one cached repo |
| POST | `/autopkg/cache/repos` | Add any public GitHub `owner/repo` to the cache (`is_custom`) |
| DELETE | `/autopkg/cache/repos/{owner}/{name}` | Remove a repo from the cache (org repos return on sync) |
| GET | `/autopkg/approvals` | List pending approvals |
| POST | `/autopkg/results/{id}/approve` | Approve or reject a result |
| POST | `/autopkg/trust/resolve-commit` | Map trust SHA-256 file hashes to a GitHub commit URL (history walk) |
| POST | `/autopkg/runs/verify-trust` | Pre-flight trust check before a run is enqueued |
| POST | `/autopkg/runs/{id}/github-context` | Attach the dispatched workflow_run id/url to a run row |
| GET | `/autopkg/recipes/{id}/runner-override.plist` | Compiled override plist the runner consumes |
| POST | `/autopkg/recipes/import-override` | Import an existing override plist (XML, base64 binary plist, YAML, or JSON) |
| POST | `/autopkg/recipes/add-override` | Create an override from an `owner/repo` + recipe identifier in the cache |
| POST | `/autopkg/recipes/{id}/verify-trust` | Re-fetch parent recipes and re-evaluate trust for one recipe |
| POST | `/autopkg/recipes/{id}/update-trust` | Persist the latest parent-recipe SHAs as a trust-change request |
| POST | `/autopkg/recipes/{id}/approve-trust` | Approve a pending trust-change request |
| GET / POST / PATCH / DELETE | `/autopkg/schedules` (and `/{id}`) | Manage cron-driven schedules; `POST /autopkg/schedules/run-due` is the optional external-cron webhook (gated by `SCHEDULE_WEBHOOK_SECRET`). |
| POST | `/autopkg/promotions/run-due` | Manually advance promotion-channel timers (also runs every minute when `SCHEDULER_ENABLED=true`). |

## Client Reporting

| Method | Path | Description |
|--------|------|-------------|
| POST | `/reports/checkin` | Client agent check-in |
| GET | `/reports/machines` | List fleet machines (paginated) |
| GET | `/reports/machines/{id}` | Get machine detail (`product_name`, `device_image_url`, `platform_uuid`, CPU fields, …) |
| GET | `/reports/compliance` | Fleet compliance overview |
| GET | `/reports/installs` | Paginated `client_install_report` rows with hostname/serial |

### POST /reports/checkin

JSON body. **`serial_number`** (string) is required.

Common top-level fields: `hostname`, `os_version`, `os_build`, `machine_model`, `cpu_type`, `cpu_arch`, `physical_cpus`, `logical_cpus`, `ram_mb`, `disk_size_gb`, `disk_free_gb`, `munki_version`, `manifest_name`, `client_identifier`, `installed_software` (array), `install_results` (array), `hardware_info` (object).

`hardware_info` may include `product_name`, `apple_image_family` (for Apple FMIP thumbnail URLs, same idea as [MunkiReport’s `get_model_icon`](https://github.com/munkireport/machine/blob/master/machine_controller.php)), `platform_uuid`, and other agent-specific keys. Unknown keys are stored as sent.

Each successful check-in appends a row to **`client_machine_checkin`** (timestamp) for per-device history and charts.

### GET /reports/machines/{id} response

Includes **`device_image_url`**: a PNG URL from Apple’s public `statici.icloud.com` / `km.support.apple.com` endpoints when the server can derive one from serial + model + `hardware_info` (mirrors MunkiReport behavior). Also **`platform_uuid`** when the agent reported `IOPlatformUUID`, and **`cpu_arch`**, **`physical_cpus`**, **`logical_cpus`** when stored on the machine row.

**`checkin_total`**: all-time count of check-ins for this machine. **`checkin_history`**: array of `{ "date": "YYYY-MM-DD", "count": number }` for the last 90 calendar days (UTC day buckets, including days with zero check-ins).

### Query parameters for GET /reports/installs

| Param | Type | Description |
|-------|------|-------------|
| page | int | Page number (default: 1) |
| page_size | int | Items per page (default: 50, max: 200) |
| search | string | Match item name, hostname, or serial |
| item_name | string | Exact Munki item name (pkginfo `name`); combined with `search` as AND |
| status | string | Exact status (e.g. `installed`, `failed`, `removed`) |

## Audit Log

| Method | Path | Description |
|--------|------|-------------|
| GET | `/audit` | List audit entries (paginated, filterable) |
| GET | `/audit/{entity_type}/{entity_id}` | Get audit trail for an entity |

### AI Insights (admin only — requires `admin.ai_insights`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/insights/query` | Natural-language fleet/Munki Q&A via Gemini tool calling. Requires `INSIGHTS_ENABLED=true` and `GEMINI_API_KEY`. |
| POST | `/insights/query/stream` | Same as above, streamed as SSE (`text-delta`, `tool`, `data`, `done` events). |

### Query Parameters for GET /audit

| Param | Type | Description |
|-------|------|-------------|
| entity_type | string | Filter by entity type |
| action | string | Filter by action |
| user_email | string | Filter by user |

## Munki repo (`/repo`, **not** under `/api/v1`)

These endpoints are what Munki clients hit via `SoftwareRepoURL`. They are mounted at the top of the app, not under `/api/v1`, but are proxied through the frontend container at `/repo/*`.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/repo/catalogs/{catalog_name}` | Compiled catalog plist (XML), filtered to `quarantine`-aware visibility. |
| GET | `/repo/manifests/{manifest_name}` | Compiled manifest plist (XML); supports nested paths. |
| GET | `/repo/icons/_icon_hashes.plist` | `icon_hashes.plist` matching what's in the `software_icon` table. |
| GET | `/repo/icons/{icon_name}` | PNG bytes from the `software_icon` table (with ETag / `If-None-Match`). |

When `MUNKI_REPO_BASIC_AUTH_USER`/`_PASSWORD` are set (env or DB via Settings), every `/repo/*` route requires HTTP Basic.

## Health and observability (top-level on the backend)

These are mounted on the **backend** container, not under `/api/v1`. The frontend container's nginx does **not** proxy them by default — hit the backend directly (e.g. `docker compose exec backend curl localhost:8000/health`) or add a `location` block to [`frontend/nginx.conf.template`](../frontend/nginx.conf.template).

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Basic health check |
| GET | `/ready` | Readiness check (includes DB) |
| GET | `/metrics` | Prometheus metrics (`prometheus-fastapi-instrumentator`) |
