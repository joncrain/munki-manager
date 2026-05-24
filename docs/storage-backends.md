# Storage backends

Munki Manager separates **where packages are served from** (an HTTPS URL Munki
clients fetch) from **how they get there** (uploaded by AutoPkg, an admin, an
in-app uploader, etc.). The serving URL is set with `MUNKI_REPO_PKG_BASE_URL`
and is the only thing that's actually wired into clients via their
`.mobileconfig`.

This means any HTTPS-reachable object store works as a backend — pick whichever
fits your environment. The three patterns documented here are AWS S3+CloudFront,
Azure Blob (+ optional Front Door), and a self-hosted Mac mini with nginx.

| Backend | Pkg URL pattern | Auth at upload | Upload tool today | Cost (small) |
|---------|-----------------|----------------|-------------------|--------------|
| AWS S3 + CloudFront | `https://d111111abcdef8.cloudfront.net/pkgs` | IAM access keys | Manual (`aws s3 cp`) or AutoPkg `S3Uploader` | $1–5/mo + egress |
| Azure Blob (+ optional Front Door) | `https://<account>.blob.core.windows.net/munki-repo/pkgs` | Managed identity (default in Terraform); SAS token; or connection string for local dev only | `POST /api/v1/autopkg/runs/{id}/pkgs` (streaming) or manual `az storage blob upload` | <$1/mo at demo scale |
| Mac mini nginx | `https://munki.example.com/pkgs` | SCP / SMB share, write to local disk | Munki admin's normal workflow | Hardware only |

> **Auto-uploader status.** The backend now ships a streaming uploader for
> AutoPkg runners *and* a direct-upload route for the `/software` page. Both
> route bytes through the configured backend (`s3` or `azure_blob`) when
> `STORAGE_BACKEND` is set, and fall back gracefully (HTTP 503 from the API,
> "skip" message from the runner) when it stays at `none`. See the section
> on [the streaming endpoints](#streaming-uploader-endpoints) below.

## Common configuration

Whichever backend you pick, set these on the backend container or in `.env`:

```sh
# The base URL Munki clients will fetch packages from. Munki appends the path
# from each pkginfo's `installer_item_location` to this.
MUNKI_REPO_PKG_BASE_URL=https://...
# Optional: where /repo/icons/* 302-redirects (defaults to serving from Postgres).
MUNKI_REPO_ICON_BASE_URL=https://...
# Optional: where Munki client_resources zips live. Defaults to swapping the
# trailing `/pkgs` path segment of MUNKI_REPO_PKG_BASE_URL with `/client_resources`.
MUNKI_REPO_CLIENT_RESOURCES_BASE_URL=
```

These are *not* HTTP redirects — Munki's downloader drops `Authorization`
headers on cross-origin 302s, so we hand the client the real URL up front.

## Streaming uploader endpoints

Two routes write through to the configured `STORAGE_BACKEND` (`azure_blob` /
`s3`). When the env var is `none` (the default), both reply with **503** so
older deployments that drive uploads externally keep working.

### `POST /api/v1/autopkg/runs/{run_id}/pkgs`

Called by `AutoPkg/scripts/report_results.py` immediately before posting the
run result. Authenticates with `Authorization: Bearer <LOCAL_RUNNER_TOKEN>`
(same model as `/pkginfo/ingest` and `/icons/ingest`). Multipart form fields:

- `file` — the pkg/dmg bytes
- `recipe_identifier` — used to build a default `pkgs/<slug>/<filename>` path
- `relative_path` — *optional* explicit override

The response includes the public URL the storage SDK returned; the runner
threads it onto the run result as `imported_pkg_url`. On the next
`/pkginfo/ingest` for the same recipe + version, the backend prefers that URL
over `MUNKI_REPO_PKG_BASE_URL + relative_path` when populating
`installer_item_location`. Munki's downloader accepts a fully-qualified URL
there.

### `POST /api/v1/munki/upload`

Backs the **Upload software** dialog on the `/software` page. Authentication
is standard JWT and gated by the `munki.software` page key (`write` access).
Multipart form fields:

- `file` — `.pkg`, `.mpkg`, or `.dmg`
- `display_name` (required), `name`, `catalogs` (comma-separated, default
  `testing`), `category`, `developer`, `description`, `unattended_install`

The backend hashes the upload, attempts a Linux-side "munkiimport-lite"
metadata extraction (xar TOC parse → `version` + `receipts` for flat
`.pkg`s), uploads the bytes to `uploaded/<slug>/<filename>` in the storage
backend, and inserts a `PkgInfo` row. When extraction can't infer a version
(typical for `.dmg` since `hdiutil` doesn't exist on Linux), the row is
flagged `pending_metadata=true` and the UI surfaces a **Manual** badge so an
admin can finish the metadata before promoting.

## Backend A — AWS S3 + CloudFront

The legacy backend. The boto3 dependency in [`backend/pyproject.toml`](../backend/pyproject.toml) keeps the door
open for an in-backend S3 uploader (see the linked plan), and the AWS settings
in `core/config.py` document the shape:

```sh
STORAGE_BACKEND=s3                     # for the future uploader
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=us-east-1
AWS_S3_BUCKET=my-munki-repo
CLOUDFRONT_DISTRIBUTION_ID=E123ABCXYZ  # optional, for cache invalidation
MUNKI_REPO_PKG_BASE_URL=https://d111111abcdef8.cloudfront.net/pkgs
```

### Bucket layout

```
s3://my-munki-repo/
├── pkgs/<recipe>/<file>.pkg
├── icons/<file>.png
└── client_resources/<file>.zip
```

CloudFront in front of the bucket gives you a friendly hostname, TLS, and a
cache for repeat downloads — Munki clients re-check the same `installer_item_location`
on every run.

### Today's workflow

Until the in-backend uploader ships, run AutoPkg with the standard
`S3Uploader` processor (or `aws s3 sync`) to land pkgs in the bucket. The
backend then references them by URL.

## Backend B — Azure Blob (+ optional Front Door)

Used by the Azure Container Apps deployment in this repo. The Terraform in
[`terraform/storage.tf`](../terraform/storage.tf) provisions the storage
account and a public-blob `munki-repo` container, and
[`terraform/containerapps.tf`](../terraform/containerapps.tf) wires the URL
into the backend automatically.

```sh
STORAGE_BACKEND=azure_blob

# Pick ONE auth path. The Azure deployment in this repo defaults to **managed
# identity** (path #3) — `terraform/storage.tf` disables shared-key auth
# (`shared_access_key_enabled = false`) and grants the apps' user-assigned
# managed identity `Storage Blob Data Contributor` on the account, so the
# connection-string and SAS-token paths are not usable in production.
#
#   1) Managed identity (default in the Terraform deployment):
AZURE_STORAGE_ACCOUNT_NAME=stmunkimanagerabcd12
# Leave SAS / connection string empty; the SDK uses DefaultAzureCredential.
#
#   2) Account name + SAS token (read-write SAS scoped to the container).
#      Use this if you need to point the backend at a storage account in a
#      different subscription where the apps' MI has no role assignment.
# AZURE_STORAGE_ACCOUNT_NAME=stmunkimanagerabcd12
# AZURE_STORAGE_SAS_TOKEN=sv=2024-...&sig=...
#
#   3) Connection string (LOCAL DEVELOPMENT ONLY).
#      Requires `shared_access_key_enabled = true` on the storage account,
#      which the deployed Terraform stack **disables** for security. Useful
#      for `docker-compose up` against a dev storage account.
# AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=https;AccountName=...;AccountKey=...;EndpointSuffix=core.windows.net

AZURE_STORAGE_CONTAINER=munki-repo
MUNKI_REPO_PKG_BASE_URL=https://stmunkimanagerabcd12.blob.core.windows.net/munki-repo/pkgs

# Optional: Azure CDN / Front Door (future, for cache invalidation parity with CloudFront)
# AZURE_CDN_PROFILE=
# AZURE_CDN_ENDPOINT=
```

### Container layout

Identical to the S3 layout — the path under the container mirrors the path
under the bucket, so any Munki tooling that builds `installer_item_location`
strings doesn't care which backend you're on.

```
https://<account>.blob.core.windows.net/munki-repo/
├── pkgs/<recipe>/<file>.pkg
├── icons/<file>.png
└── client_resources/<file>.zip
```

### Today's workflow

The streaming uploader (`POST /api/v1/autopkg/runs/{id}/pkgs`) does the
upload through the backend's managed identity — no operator-side credentials
needed for the AutoPkg path. For one-off operator uploads:

```sh
# Use --auth-mode login (AAD) instead of --auth-mode key. Shared-key auth
# is disabled on the storage account.
az storage blob upload-batch \
  --account-name stmunkimanagerabcd12 \
  --destination munki-repo \
  --destination-path pkgs \
  --source ./out/pkgs \
  --auth-mode login
```

You'll need `Storage Blob Data Contributor` on the account (granted via
`az role assignment create --role "Storage Blob Data Contributor" ...`). And
your operator IP must be in `var.operator_ip_allowlist` because the storage
account firewall denies management-plane access by default.

Anonymous blob read is on at the container level (`container_access_type =
"blob"` in Terraform), so Munki clients fetch without credentials. Listing the
container is *not* anonymous — that's deliberate.

### Storage account hardening

The deployed Terraform stack now applies these defenses (see
`terraform/storage.tf`):

- `shared_access_key_enabled = false` — account-key auth is off; only AAD
  identities can write.
- The Container Apps managed identity holds `Storage Blob Data Contributor`
  on the account.
- Account firewall denies by default; only the Container Apps env's
  outbound IP and `var.operator_ip_allowlist` may issue
  authenticated/management requests.
- `min_tls_version = "TLS1_2"` is pinned.

Public anonymous reads against the `munki-repo` container are unaffected by
the firewall (Microsoft documents this exception for blob-anonymous
containers).

### Public-blob caveat

The `munki-repo` container is publicly readable. Any URL someone learns is
fetchable from anywhere on the public internet. This matches the typical
"signed-URL CloudFront" deployment in security posture — you rely on the
filenames being unguessable, not on auth. If you need real auth on package
downloads, switch to SAS-token URLs and have the backend mint short-lived ones
on demand. See finding 2.3.1 in [`docs/security-overview.md`](./security-overview.md).

## Backend C — Mac mini nginx (self-hosted)

Documented in [`mac-mini-deployment.md`](mac-mini-deployment.md). The
distinguishing feature is that pkgs land on local disk through the admin's
normal `munkiimport` / SMB share workflow, and nginx serves them directly. No
object storage, no cost, no upload step — but you also get no CDN, no
geographic distribution, and a single point of failure.

```sh
MUNKI_REPO_PKG_BASE_URL=https://munki.example.com/pkgs
# No STORAGE_BACKEND, no cloud creds. The auto-uploader is irrelevant here
# because pkgs already exist on disk before they need to be served.
```

## Switching backends

The wire-format compatibility means you can move between backends by:

1. Copying the existing `pkgs/`, `icons/`, and `client_resources/` directories
   to the new store (`aws s3 sync` ↔ `az storage blob upload-batch` ↔ `rsync`).
2. Updating `MUNKI_REPO_PKG_BASE_URL` in the backend's environment.
3. Restarting the backend.
4. Letting clients re-fetch on their next `managedsoftwareupdate` run — they'll
   pick up the new `PackageURL` from their refreshed mobileconfig and download
   from the new origin.

If you've baked the URL into clients via Munki's `SoftwareRepoURL` directly
(some self-hosted deployments do this), you'll need to re-enroll or push a
profile update through your MDM.

## Choosing a backend

| If you... | Pick |
|----------|------|
| Are deploying via the Terraform in this repo | **Azure Blob** (it's already wired) |
| Already run on AWS and have CloudFront in front of an S3 bucket | **S3 + CloudFront** |
| Want zero recurring cloud cost and have a Mac mini already | **Mac mini nginx** |
| Need real auth on package downloads | None of the above as-is. The Mac mini setup with `MUNKI_REPO_BASIC_AUTH_USER` / `MUNKI_REPO_BASIC_AUTH_PASSWORD` only authenticates `/repo/*` on the app, but if `pkgs/` is served by the same nginx, requiring HTTP Basic on that location too works (Munki forwards `AdditionalHttpHeaders` to every host). Otherwise wait for SAS-URL support in the planned uploader. |
