# Security Overview

**Last reviewed:** 2026-05-11 (re-reviewed after the first remediation pass)
**Scope:** Munki Manager backend + frontend, AutoPkg integration, and the
  Azure deployment defined in `terraform/`.

> **Status update — first remediation pass complete.** The two highest-risk
> findings are now closed in code/Terraform and pending operator apply:
>
> - **Finding 1.2 (Critical) — public AutoPkg ingest endpoints:** ✅ Fixed.
>   `/pkginfo/ingest`, `/icons/ingest`, and the `/runs/{id}/{results,complete,github-context}`
>   webhooks are no longer on the public allowlist; they require the
>   `LOCAL_RUNNER_TOKEN` Bearer (or a user JWT). Cloud-runner workflow forwards
>   the token from `secrets.MUNKI_MANAGER_RUNNER_TOKEN`. Regression coverage
>   is in `backend/tests/test_pkg_upload_rbac.py`.
> - **Finding 2.3.2 (High) — shared-key auth on storage:** ✅ Fixed and
>   applied. `shared_access_key_enabled = false` on the storage account; apps'
>   managed identity holds `Storage Blob Data Contributor` on the account
>   scope; the `azure-storage-connection-string` Key Vault secret has been
>   destroyed; backend Container App rolled to a managed-identity-only
>   revision. Provider uses `storage_use_azuread = true` for state-refresh
>   reads and the operator AAD identity holds the four storage data-plane
>   roles (Blob Owner / Queue / Table / File Privileged) at the RG scope.
> - **Finding 2.3.3 (High) — no firewall on storage account:** ⚠️ Code is
>   in place but the firewall is **opt-in** via `var.operator_ip_allowlist`
>   to avoid locking the operator out of subsequent Terraform refreshes.
>   To enable: list your laptop / CI public IP(s) in
>   `operator_ip_allowlist`, then `terraform apply`. The CA env's static
>   outbound IP is added automatically.
> - **Finding 2.3.1 (High) — anonymous public-read on the Munki container:**
>   Still open. Mitigations: token-signed URLs via Front Door, or proxy
>   `/repo/pkgs/*` through the backend with short-lived SAS minting.

This document is a snapshot of the security posture of Munki Manager as it
ships today. It is split into two sections:

1. [Application security](#1-application-security) — the FastAPI backend, the
   Vite SPA, the `/repo` Munki endpoints, and the AutoPkg/cloud-runner
   webhooks.
2. [Azure deployment security](#2-azure-deployment-security) — the Terraform
   stack in `terraform/` (Container Apps, Postgres Flexible Server, Key Vault,
   ACR, and the storage account that hosts the Munki repo).

Severity labels follow a simple convention:

- **Critical** — exploitable today by a remote unauthenticated attacker, with
  high impact on Munki client integrity (i.e. arbitrary software installs on
  managed Macs) or full data exfiltration.
- **High** — easily exploitable post-credential-leak, or a single
  misconfiguration away from Critical.
- **Medium** — defense-in-depth gaps, predictable post-authentication abuse,
  or significant blast-radius issues if a related secret leaks.
- **Low** — hardening / hygiene; not exploitable on its own.

---

## 1. Application security

### 1.1 What's in scope

| Component                                  | Path                                           | Auth model                                                 |
| ------------------------------------------ | ---------------------------------------------- | ---------------------------------------------------------- |
| Public SPA                                 | `frontend/`                                    | JWT in `localStorage`, sent as `Authorization: Bearer`     |
| `/api/v1/*` REST surface                   | `backend/automunki/api/routes/`                | `RBACMiddleware` (`backend/automunki/core/rbac_middleware.py`) |
| `/repo/*` (Munki client repo)              | `backend/automunki/api/routes/repo.py`         | `RepoBasicAuthMiddleware` (HTTP Basic, optional)           |
| AutoPkg ingest (cloud + local runner)      | `POST /api/v1/autopkg/...`                     | Public allowlist + `LOCAL_RUNNER_TOKEN` Bearer             |
| Direct admin upload (`.pkg` / `.dmg`)      | `POST /api/v1/munki/upload`                    | RBAC (`munki.software` `write`)                            |
| Schedule / promotion webhooks              | `POST /api/v1/autopkg/schedules/run-due` etc.  | `X-Schedule-Secret` header                                 |
| OIDC SSO                                   | `backend/automunki/api/routes/oidc.py`         | Configurable IdP                                           |

### 1.2 Authentication & authorization

The auth model is layered:

1. `AUTH_MODE` (env var) selects `disabled` / `jwt` / `oidc`. In production
   the deployed Container App sets `AUTH_MODE=jwt` (see
   `terraform/containerapps.tf`). When `disabled`, **every** `/api/v1`
   request is treated as the synthetic `dev@example.com` superuser
   (`DEV_USER_PRINCIPAL` in `rbac_middleware.py`). This is intentional for
   local dev but is a footgun in any non-dev environment.
2. JWT issuance uses `fastapi-users` with `JWTStrategy(secret=settings.secret_key)`
   (`backend/automunki/core/security.py`). Lifetime defaults to 1 hour.
3. RBAC is enforced in `RBACMiddleware`: every non-public path is mapped to a
   `page_key` (`backend/automunki/core/page_keys.py`) and the user's
   effective permissions decide read vs. write.
4. The `LOCAL_RUNNER_TOKEN` Bearer is accepted on a small allowlist of
   AutoPkg-runner paths (constant-time compared with `hmac.compare_digest`).

The single biggest application-layer concern is the **public allowlist** in
`_is_public_path()` (`rbac_middleware.py:77-120`):

```117:120:backend/automunki/core/rbac_middleware.py
    if path.rstrip("/") == "/api/v1/autopkg/pkginfo/ingest" and method == "POST":
        return True
    if path.rstrip("/") == "/api/v1/autopkg/icons/ingest" and method == "POST":
        return True
```

```112:116:backend/automunki/core/rbac_middleware.py
    if path.startswith("/api/v1/autopkg/runs/") and (
        "/results" in path or path.rstrip("/").endswith("/complete") or path.rstrip("/").endswith("/github-context")
    ):
        return True
```

Combined, that means **five POST endpoints accept arbitrary input from
unauthenticated callers on the public Container App URL**:

- `POST /api/v1/autopkg/pkginfo/ingest` — creates/updates a `PkgInfo` row,
  which then becomes part of catalogs and therefore part of every client's
  install plan. The handler does not require a matching `recipe_identifier`;
  a plist with `name`, `version`, and `installer_item_location` is enough
  (`autopkg.py:2204` onwards).
- `POST /api/v1/autopkg/icons/ingest` — overwrites a `software_icon` blob.
- `POST /api/v1/autopkg/runs/{id}/results` — adds an `AutoPkgRunResult` to
  any UUID (404 if unknown but otherwise unauthenticated).
- `POST /api/v1/autopkg/runs/{id}/complete` — marks any run completed.
- `POST /api/v1/autopkg/runs/{id}/github-context` — overwrites the GitHub
  Actions URL associated with a run.

The intent (per the comment in `rbac_middleware.py:67-73`) was that the
`LOCAL_RUNNER_TOKEN` becomes the auth path and these public allowlist
entries fall away once every runner is updated. That hasn't happened yet,
so today they are still wide open.

The `installer_item_location` ingestion for `POST /pkginfo/ingest` will
override-resolve to a runner-uploaded URL (`autopkg.py:2245-2271`) when a
matching `AutoPkgRunResult.imported_pkg_url` exists, but if no run-result
exists the plist's URL/path is used unchanged. **An attacker can therefore
inject a pkginfo whose `installer_item_location` is an attacker-controlled
HTTPS URL.** Whether this leads to client-side execution depends on whether
the chosen `name` / `version` lands the entry in a catalog any client
manifest references — but the attacker controls those fields too.

**Severity: Critical.**

### 1.3 Open registration

`AUTH_REGISTRATION_OPEN=true` is hard-coded in `terraform/containerapps.tf`
for the deployed env. With `AUTH_MODE=jwt`, anyone on the internet can hit
`POST /api/v1/auth/register` and create an account; new users are auto-granted
the seeded `Viewer` role (`security.py:UserManager.on_after_register`). The
Viewer role grants read access to every page key (see
`backend/automunki/services/permissions.py` — verify the seeded scopes).

Practical impact: the entire catalog, manifest list, software inventory,
audit log, and AutoPkg history is readable by anyone who registers. Consider
that this is, in practice, a list of every package version your fleet runs
plus enough metadata to fingerprint what is and isn't patched.

**Severity: High.**

### 1.4 OIDC

Two notable issues in `backend/automunki/api/routes/oidc.py`:

- The `nonce` generated in `oidc_authorize` is sent to the IdP but never
  verified against an ID token in `oidc_callback`. The `state` JWT only
  contains random bytes (`secrets.token_hex(16)`) and isn't bound to a
  session, so a captured state can be reused. **Severity: Medium**
  (anti-CSRF-on-callback gap).
- The issued JWT is returned to the SPA via the URL query string:
  `RedirectResponse(url=f"{base}/auth/callback?token={jwt_token}")`. URL
  query strings end up in browser history, referer headers (when the SPA
  immediately fetches anything cross-origin), Cloudflare access logs, and
  Application Insights logs. **Severity: Medium.**

### 1.5 JWT storage on the client

The SPA reads/writes the token via `localStorage` (`auth-provider.tsx:49`,
`123`). This is the standard SPA pattern, but it makes the token reachable
from any successful XSS. There is no Content-Security-Policy in
`frontend/nginx.conf.template`, so the only XSS defense is React's
auto-escaping. **Severity: Medium.**

### 1.6 Password policy

`UserManager` (`backend/automunki/core/security.py`) does not override
`validate_password`, so the only requirement is fastapi-users' default
(non-empty). There is no rate limit on `POST /auth/login`, no account
lockout, and no audit-trigger on repeated failures. **Severity: Medium.**

### 1.7 Rate limiting

There is **no application-layer rate limiting** anywhere — no `slowapi`,
no per-IP throttle, no per-user quota. The only rate-limit-aware code is
client code that consumes the GitHub API. **Severity: Medium** (impacts
auth brute force, the public `pkginfo/ingest`, and the schedule webhook).

### 1.8 `/repo` Basic Auth

`RepoBasicAuthMiddleware` (`backend/automunki/core/repo_basic_auth_middleware.py`)
gates `/repo/*` only when credentials are configured (env or DB). When both
are unset, `/repo` is fully anonymous — which is the expected Munki model
but means manifests, catalogs, and ICONs are world-readable from the
Container App URL. The actual pkg downloads happen against the storage
account directly (see §2.4). **Severity: Low** by design, but worth noting.

### 1.9 Schedule webhook secret comparison

The webhook handlers compare with `==`:

```598:599:backend/automunki/api/routes/autopkg.py
    if not x_schedule_secret or x_schedule_secret != settings.schedule_webhook_secret:
        raise HTTPException(status_code=403, detail="Invalid schedule secret")
```

Should use `hmac.compare_digest` to match the `LOCAL_RUNNER_TOKEN` path
(`rbac_middleware.py:165`). **Severity: Low.**

### 1.10 CORS

`backend/automunki/main.py:82-88` registers CORS with
`allow_origins=settings.cors_origins`, `allow_methods=["*"]`,
`allow_headers=["*"]`, `allow_credentials=True`. This is fine because
`cors_origins` is locked to the public app URL in the deployed env, but the
broad methods/headers means any future origin you add inherits a permissive
policy. **Severity: Low.**

### 1.11 OpenAPI exposure

`/api/docs` and `/api/openapi.json` are public (`rbac_middleware.py:82-83`).
This is convenient but means the full API schema, including admin endpoints,
is enumerable. **Severity: Low.**

### 1.12 Security headers

`frontend/nginx.conf.template` sets none of: `Strict-Transport-Security`,
`Content-Security-Policy`, `X-Frame-Options`, `X-Content-Type-Options`,
`Referrer-Policy`. **Severity: Low.**

### 1.13 Path traversal on uploads

`backend/automunki/services/storage/base.py:sanitize_relative_path()` rejects
absolute paths and `..` segments before any backend write. Direct admin
upload (`munki_upload.py`) routes through `_safe_filename()` and `_slug()`
in `services/munki_import.py`, both of which strip non-`\w.-` characters.
This is correctly handled today. ✅

### 1.14 SSRF in OIDC token exchange

`oidc_callback` posts to `settings.oidc_token_endpoint` and
`settings.oidc_userinfo_endpoint`. These are operator-controlled, not
attacker-controlled, so SSRF is not possible from inputs. ✅

---

## 2. Azure deployment security

### 2.1 Topology

```
                        ┌──────────────────────────────────┐
       Internet ───────►│  Container Apps env (public)     │
                        │   ├── frontend (nginx, ext)      │
                        │   └── backend  (FastAPI, ext)    │
                        └──────────────┬───────────────────┘
                                       │ MI auth
                ┌───────────┬──────────┼──────────────────┐
                ▼           ▼          ▼                  ▼
       ┌──────────────┐ ┌────────┐ ┌──────────┐  ┌────────────────┐
       │ Key Vault    │ │  ACR   │ │ Postgres │  │ Storage Account│
       │ (RBAC, pub)  │ │ (Basic)│ │ (pub +   │  │  munki-repo/   │
       │              │ │        │ │  AllAzure│  │  (anon-blob,   │
       │              │ │        │ │  rule)   │  │  shared key)   │
       └──────────────┘ └────────┘ └──────────┘  └────────────────┘
                                                         ▲
                                                         │ HTTPS, anonymous
                                                  ┌──────┴──────┐
                                                  │ Mac fleet   │
                                                  │ (Munki)     │
                                                  └─────────────┘
```

### 2.2 Identity & secrets

Single user-assigned managed identity (`id-munkimanager-apps`) is shared by
both Container Apps and is granted:

- `AcrPull` on the registry (`registry.tf:15-19`)
- `Key Vault Secrets User` on the vault (`keyvault.tf:32-36`)

Secrets in Key Vault: `app-secret-key`, `postgres-password`, `database-url`,
`github-token`, `local-runner-token`, `slack-webhook-url`,
`azure-storage-connection-string`. Container Apps fetches them as
`secret { ... key_vault_secret_id = ... }` references.

This part is sane. ✅

### 2.3 Storage account — the Munki package store

This is the asset you specifically called out. The relevant Terraform is in
`terraform/storage.tf`. Findings, in priority order:

#### 2.3.1 Anonymous-read on the `munki-repo` container

```49:53:terraform/storage.tf
resource "azurerm_storage_container" "munki_repo" {
  name                  = "munki-repo"
  storage_account_id    = azurerm_storage_account.repo.id
  container_access_type = "blob" # anonymous read on individual blobs (not list)
}
```

`container_access_type = "blob"` means **anyone on the internet who knows
or guesses a blob name can fetch it**. List is disabled, but blob names are
predictable: the runner uploads to `pkgs/<recipe_slug>/<filename>.pkg`
(`autopkg.py:679`). The recipe slug is the AutoPkg recipe identifier (e.g.
`com.github.autopkg.recipes.GoogleChrome.munki`), and the filename is the
package's actual name. Both are easy to guess for any popular software.

This matches the existing S3+CloudFront model (anonymous public reads) and
is necessary because the Munki client doesn't authenticate by default and,
critically, **drops `Authorization` headers across cross-origin 302s**
(see the comment on `MUNKI_REPO_PKG_BASE_URL` in
`backend/automunki/core/config.py:73-77`). So we can't easily put the
storage account behind an authenticated proxy without breaking the client.

What we *can* do is put a CDN with token-signed URLs (CloudFront / Azure
Front Door custom rules) in front, and rotate the signing key. That is the
real fix; see the remediation plan.

**Severity: High** — it's an intentional design choice but the impact is
real:

- License compliance: every package you cache in the repo (1Password,
  proprietary apps, etc.) is downloadable by anyone, anywhere.
- Inventory disclosure: an attacker who knows your domain can enumerate
  the popular AutoPkg recipe paths and learn what versions you ship.
- Asymmetric load: you pay storage egress for the world.

#### 2.3.2 Shared-key auth is enabled

`shared_access_key_enabled` is not set, so it defaults to `true`. The
backend currently authenticates with `AZURE_STORAGE_CONNECTION_STRING`,
which is a connection string carrying the **primary account key**:

```95:102:terraform/keyvault.tf
resource "azurerm_key_vault_secret" "azure_storage_connection_string" {
  name         = "azure-storage-connection-string"
  value        = azurerm_storage_account.repo.primary_connection_string
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [azurerm_role_assignment.operator_kv_admin]
}
```

The account key grants **full** storage account access — read + write +
delete + container administration on every container in the account, plus
the ability to mint SAS tokens. A single compromise (logged exception,
debug dump of env vars, KV exfiltration) hands the entire repo to the
attacker. The `azure_blob.py` backend already supports
`DefaultAzureCredential` (`azure_blob.py:62-69`), so we can move to managed
identity and **disable shared keys entirely**.

**Severity: High.**

#### 2.3.3 No firewall on the storage endpoint

`public_network_access_enabled = true` and there is no `network_rules`
block, so the storage endpoint is reachable from any IP on the internet.
Combined with §2.3.2, this means an attacker who acquires the account key
from anywhere does not need to be on a trusted network to use it.

For the public Munki container we cannot lock this down without breaking
clients. For everything else (the `azure-storage-connection-string` is also
the key for any future container in the same account) it should be locked
to the Container Apps environment outbound IPs and operator IPs.

**Severity: High** when combined with §2.3.2; **Medium** alone.

#### 2.3.4 `min_tls_version` not pinned

Defaults to `TLS1_2` on the current `azurerm` provider, so we're OK today,
but pinning it explicitly is cheap and protects against a provider default
regression.

**Severity: Low.**

#### 2.3.5 `allow_nested_items_to_be_public = true`

Required for the public container, but it means any future container that
gets created in this account can also be set to public. We should plan to
either (a) move private artifacts to a second storage account, or (b)
operationally enforce that nothing else is created here.

**Severity: Low.**

#### 2.3.6 App auto-creates the container on every upload

`azure_blob.py:101-104`:

```python
try:
    await container.create_container()
except Exception:
    pass
```

This requires the SP to hold container-create rights, which broadens what
the credential can do. With managed identity (per §2.3.2 fix) this should
be removed and the container should be a Terraform-managed resource only.

**Severity: Low.**

### 2.4 Postgres Flexible Server

`terraform/postgres.tf`:

#### 2.4.1 "AllowAllAzureServices" rule + public network access

```50:55:terraform/postgres.tf
resource "azurerm_postgresql_flexible_server_firewall_rule" "allow_azure" {
  name             = "AllowAllAzureServices"
  server_id        = azurerm_postgresql_flexible_server.main.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}
```

The 0.0.0.0/0.0.0.0 magic rule does **not** mean "your subscription's
Azure resources" — it means **any resource in any Azure tenant** can
attempt to connect to the server. The only thing standing between an
attacker and the database is the password (which is in Key Vault, but is
also baked into the `database-url` secret and can therefore be exfiltrated
the same way the storage key can). There's no AAD auth and no IP allowlist
beyond the magic rule.

The cheap fix is to scope the rule to the Container Apps environment's
static outbound IP (already exposed in `terraform/outputs.tf` per the
backend's ingress comment). The proper fix is a private endpoint /
delegated VNet.

**Severity: High.**

#### 2.4.2 SSL is requested by the client, not enforced by the server

`database_url` includes `?ssl=require` (`keyvault.tf:62-68`), so the
backend opens TLS sessions. There's no equivalent server-side enforcement
configured (`require_secure_transport` is not set; the Flexible Server
default in current API versions is `ON`, but verify with
`az postgres flexible-server show` and pin it in Terraform).

**Severity: Medium.**

#### 2.4.3 Admin password is in `terraform.tfvars` on the operator's laptop

`var.postgres_admin_password` is sensitive in Terraform but is supplied via
`terraform.tfvars` on the operator's machine. State (`terraform.tfstate`)
is local and contains the password too. Both files are gitignored, but
laptop loss = password exposure.

**Severity: Medium.**

### 2.5 Key Vault

`terraform/keyvault.tf`:

- `purge_protection_enabled = false` and `purge_soft_delete_on_destroy =
  true` — `terraform destroy` permanently deletes every secret with no
  recovery window.
- `public_network_access_enabled = true` — KV is reachable from anywhere
  on the internet; only RBAC stops access.
- `soft_delete_retention_days = 7` — fine; the bigger issue is that purge
  protection is off.

The Key Vault Secrets Officer assignment (`operator_kv_admin`) is
unconditionally granted to whoever runs `terraform apply`. That's the
operator's UPN/SP, which is fine, but consider that any TF runner you ever
run from inherits this role.

**Severity: Medium** for the lack of purge protection; **Medium** for
public network access.

### 2.6 Container Apps

#### 2.6.1 Backend is publicly reachable

The backend's ingress is `external_enabled = true` (with the comment
`containerapps.tf:120-133` acknowledging this is a workaround). So the
backend FQDN is reachable directly from the internet, not just through the
frontend nginx. The only protection is `RBACMiddleware`. That's fine for
authenticated routes, but combined with the unauthenticated AutoPkg
endpoints (§1.2) it means the public AutoPkg ingest is two URLs not one.

The fix the comment suggests — `ip_security_restriction` limited to the
Container Apps environment static IP — is straightforward but not yet
implemented.

**Severity: Medium.**

#### 2.6.2 Internal traffic is HTTP

`allow_insecure_connections = true` and `transport = "http"` on the
backend ingress. Inside the Container Apps environment this is acceptable
(traffic stays on the Azure backbone within the env), but a misrouted /
captured request would carry the `Authorization` header in cleartext.

**Severity: Low.**

### 2.7 Container Registry

- `admin_enabled = false` ✅
- `Basic` SKU ✅ (no Microsoft Defender for Containers / Trivy scanning)
- No image signing (`cosign`, `notation`) and no Container Apps policy that
  requires signed images. Anyone with `AcrPush` can push any image.

**Severity: Low** today — the only `AcrPush` holder is the GitHub OIDC
federated SP, but this becomes important as soon as a second pusher exists.

### 2.8 GitHub Actions

#### 2.8.1 Federated OIDC to Azure

`.github/workflows/deploy.yml` uses OIDC + `vars.AZURE_CLIENT_ID` /
`vars.AZURE_TENANT_ID` / `vars.AZURE_SUBSCRIPTION_ID`. This is the right
shape (no long-lived service principal secret). The federated credential
on the SP needs to be scoped to a specific repo + branch (`subject` claim
should be `repo:OWNER/REPO:ref:refs/heads/main` or
`repo:OWNER/REPO:environment:prod`), otherwise any workflow in any branch
can request a token. **Verify out-of-band** in the Entra ID portal.

**Severity: Medium** if the federated credential is broadly scoped.

#### 2.8.2 Action pinning

- `deploy.yml` and `checks.yml` pin actions to commit SHAs ✅
- `autopkg_cloud_runner.yml` pins to tags only:
  - `actions/checkout@v6`
  - `astral-sh/setup-uv@v7`
  - `joncrain/macos-pkg-install@v1.0` (third-party!)
  - `actions/upload-artifact@v7`
  - The `joncrain/macos-pkg-install` action is fetched as a release tag,
    which can be retargeted to a different commit at any time.

**Severity: Medium** for the third-party action, **Low** for the official
ones.

#### 2.8.3 Workflow inputs interpolated into shell

`autopkg_cloud_runner.yml` passes `inputs.recipe` via the `env:` block
(safe). `inputs.api_url` becomes `BACKEND_URL` and is `curl`'d. Both are
operator-supplied via `workflow_dispatch`, which is gated by repo write
access, so direct exploitation requires push access. **Severity: Low.**

### 2.9 Terraform state

`terraform.tfstate` is local (not in a remote backend). It contains every
secret in plaintext (postgres password, Slack webhook, GitHub PAT, etc.).
Loss or accidental commit of the state file leaks everything. The
`.gitignore` covers it but a remote backend with Azure Storage + state lock
would be safer.

**Severity: Medium.**

### 2.10 Untracked artifacts in the working tree

`backend/_squash_sql_err.txt` and `backend/_squash_sql_out.txt` are not
gitignored. They look like alembic migration squash logs (no secrets in the
samples checked) but should be added to `.gitignore` to prevent accidental
commit. **Severity: Low.**

---

## 3. Findings summary

| #     | Area    | Finding                                                         | Severity |
| ----- | ------- | --------------------------------------------------------------- | -------- |
| 1.2   | App     | Public AutoPkg ingest endpoints (pkginfo/icons/results/complete) | Critical |
| 1.3   | App     | Open registration on internet-facing app                        | High     |
| 1.4   | App     | OIDC nonce not validated                                        | Medium   |
| 1.4   | App     | OIDC issues JWT via URL query string                            | Medium   |
| 1.5   | App     | JWT in localStorage with no CSP                                 | Medium   |
| 1.6   | App     | No password complexity / lockout                                | Medium   |
| 1.7   | App     | No application-layer rate limiting                              | Medium   |
| 1.9   | App     | Schedule secret compared with `==` not `compare_digest`         | Low      |
| 1.10  | App     | CORS `allow_methods=["*"]` / `allow_headers=["*"]`              | Low      |
| 1.11  | App     | OpenAPI / Swagger UI public                                     | Low      |
| 1.12  | App     | No security headers (HSTS / CSP / etc.)                         | Low      |
| 2.3.1 | Storage | Anonymous public-read container (Munki repo)                    | High     |
| 2.3.2 | Storage | Shared-key auth enabled; primary key in Key Vault               | High     |
| 2.3.3 | Storage | No storage account firewall                                     | High*    |
| 2.3.4 | Storage | `min_tls_version` not pinned                                    | Low      |
| 2.3.5 | Storage | `allow_nested_items_to_be_public = true`                        | Low      |
| 2.3.6 | Storage | App auto-creates container on every upload                      | Low      |
| 2.4.1 | Postgres| `AllowAllAzureServices` rule + public network                   | High     |
| 2.4.2 | Postgres| SSL required by client, not enforced by server                  | Medium   |
| 2.4.3 | Postgres| Admin password in operator-side tfvars / state                  | Medium   |
| 2.5   | KV      | `purge_protection = false`                                      | Medium   |
| 2.5   | KV      | Key Vault public network access                                 | Medium   |
| 2.6.1 | CA      | Backend ingress is external                                     | Medium   |
| 2.6.2 | CA      | Backend ingress is plain HTTP (intra-env)                       | Low      |
| 2.7   | ACR     | No image scanning / signing                                     | Low      |
| 2.8.1 | CI      | Federated OIDC scope must be verified                           | Medium   |
| 2.8.2 | CI      | Third-party `joncrain/macos-pkg-install@v1.0` not pinned to SHA | Medium   |
| 2.9   | TF      | Local state file with plaintext secrets                         | Medium   |
| 2.10  | Repo    | Untracked SQL log files not in `.gitignore`                     | Low      |

*High when combined with 2.3.2; Medium alone.

The **two findings that demand attention now** are:

- **1.2 — Public AutoPkg ingest.** This lets any internet attacker plant a
  `PkgInfo` row whose `installer_item_location` they control. With a
  carefully chosen `name` matching a real catalog item, this becomes a
  software-supply-chain vector against every Munki client that subscribes
  to the affected catalog. Fix immediately.
- **2.3.1 + 2.3.2 + 2.3.3 — the storage account triangle.** Public reads
  on the package container are a license-compliance / inventory-disclosure
  problem you may already be aware of, but the bigger blast radius is the
  account key in Key Vault with no storage-side firewall: any leak of that
  secret = full storage account compromise from anywhere.
