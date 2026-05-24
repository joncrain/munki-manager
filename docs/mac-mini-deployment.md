# Munki Manager on a Mac mini (Docker + local packages)

This guide walks through a **single-machine** deployment: a Mac mini runs **Docker Compose** (Postgres, API, web UI), stores **installer packages and icons on local disk**, and optionally exposes that tree over **SMB** for admins. Munki clients use **HTTPS** to the same host; **reporting** uses the Swift postflight agent described in [`agent/README.md`](../agent/README.md).

## What you get

| Layer | Role |
|--------|------|
| **React SPA + nginx** (port 3000 in Compose) | Web UI; nginx serves the Vite build and proxies `/api/*`, `/repo/*`, `/icons/*` to the API ([`docs/deployment.md`](./deployment.md)) |
| **FastAPI** | Catalogs, manifests, and icons compiled/served from Postgres; does **not** serve `pkgs/` or `client_resources/` |
| **PostgreSQL** | Database (Docker volume) — stores catalogs, manifests, pkginfo, and **software icons** (PNG) |
| **Static file URL** (nginx or similar) | Serves `pkgs/` and `client_resources/` from disk — Munki clients fetch these directly |

Packages are **not** stored in Postgres. Munki Manager expects **pkginfo** in the database (from the UI or AutoPkg import) and **installer files** on disk at paths that match the `installer_item_location` (and similar) fields in that pkginfo. Enrolled clients download them directly from the URL configured as Munki's `PackageURL`; the app itself doesn't proxy or redirect `/repo/pkgs/*` any more. The URL is written into the client's `.mobileconfig` at enrollment and is managed in **Settings → Package & client resource URLs** (or pinned via `MUNKI_REPO_PKG_BASE_URL`).

> Why no redirect? Munki's downloader (`gurl`) drops `Authorization` headers on cross-origin 302s, so any deployment with the pkg host on a different origin than the app would fail with 401. Going direct sidesteps that entirely.

**Icons** (PNG) live in the `software_icon` table and are streamed directly from `/repo/icons/<name>.png` with proper ETags plus a real `_icon_hashes.plist` for client-side caching. Upload happens via the UI (**Software → Upload PNG**) or by bulk-ingesting an existing `icons/` directory once with `automunki ingest-icons <dir>`. `MUNKI_REPO_ICON_BASE_URL`, if set, still takes precedence and redirects to an external CDN/bucket — leave it unset to serve from the DB.

## Architecture (one host)

```
Clients (Munki + postflight)
         │ HTTPS
         ▼
┌────────────────────────────────────────────────────────────┐
│ Mac mini                                                   │
│  ┌──────────────┐     ┌─────────┐     ┌──────────────┐     │
│  │ Reverse proxy│ ──► │ SPA+nx  │ ──► │ FastAPI + DB │     │
│  │ :443 / :80   │     │  :3000  │     │  (Docker)    │     │
│  └──────┬───────┘     └─────────┘     └──────────────┘     │
│         │                                                  │
│         │ /pkgs (static)                                   │
│         ▼                                                  │
│  /var/munki-manager/munki-data/{pkgs,pkgsinfo,...}             │
│  (icons served from Postgres via /repo/icons/*)            │
│         ▲                                                  │
│         │ optional SMB share for admins                    │
└────────────────────────────────────────────────────────────┘
```

AutoPkg can run **on the same Mac mini** (local runner) or **GitHub Actions**; see [`docs/local-autopkg-runner.md`](./local-autopkg-runner.md).

---

## 1. Prepare the Mac mini

1. **macOS** current enough for [Docker Desktop](https://docs.docker.com/desktop/setup/install/mac-install/) (Apple Silicon or Intel).
2. **Hostname and DNS**: Give the server a stable name on your network, e.g. `munki.internal` or `munki.corp.example.com`, via DNS or split DNS / `/etc/hosts` on clients.
3. **Disk**: Use a large APFS volume for package storage (e.g. `/var/munki-manager/munki-data` or an external volume). Hundreds of GB is common for a software repo.
4. **Firewall**: Allow **TCP 80** and **443** (and **3000** only if you test without a reverse proxy) from client subnets.

---

## 2. Install Docker and clone the repo

```bash
# Install Docker Desktop (GUI), then verify:
docker compose version

git clone https://github.com/joncrain/munki-manager.git
cd munki-manager
cp .env.example .env
```

---

## 3. Directory layout for packages and icons

Create a **Munki repo root** on disk (this is what AutoPkg’s `MUNKI_REPO` will point at when you use the local runner):

```bash
sudo mkdir -p /var/munki-manager/munki-data
sudo chown -R "$USER":staff /var/munki-manager/munki-data

mkdir -p /var/munki-manager/munki-data/pkgs \
         /var/munki-manager/munki-data/client_resources \
         /var/munki-manager/munki-data/pkgsinfo \
         /var/munki-manager/munki-data/AutoPkg/Overrides
```

Typical layout:

- **`pkgs/`** — `.dmg`, `.pkg`, etc. (often under `pkgs/apps/...` per recipe `MUNKI_REPO_SUBDIR`).
- **`pkgsinfo/`** — plist files created by **MunkiImporter** when AutoPkg runs; Munki Manager’s database is still the source of truth for what the web UI edits, but AutoPkg compares against on-disk pkginfo here.
- **Icons** live in the **database** (`software_icon` table), not on disk — see below.

You will expose **`pkgs/`** via a **static URL** (next section). The **HTTP path** you choose must match how you set `MUNKI_REPO_PKG_BASE_URL`.

**Recommended URL mapping:**

- `MUNKI_REPO_PKG_BASE_URL` = `https://YOUR_HOST/pkgs`
  → physical files live under `/var/munki-manager/munki-data/pkgs/` (nginx serves `location /pkgs/` → that folder).
- **Icons**: leave `MUNKI_REPO_ICON_BASE_URL` **unset**. The backend serves `/repo/icons/<name>.png` directly from Postgres (with real ETags and a `_icon_hashes.plist`) — no nginx alias needed. Upload via the UI (**Software → Upload PNG**) or bulk-ingest an existing on-disk `icons/` directory once:

  ```bash
  # From inside the backend container, or anywhere the DATABASE_URL is reachable:
  docker compose exec backend automunki ingest-icons /path/to/icons
  # …or re-ingest, overwriting existing rows:
  docker compose exec backend automunki ingest-icons /path/to/icons --overwrite
  ```

  Set `MUNKI_REPO_ICON_BASE_URL=https://cdn.example.com` only if you want to redirect icons to an external host (S3/CloudFront); when set, it takes precedence over the DB.

If you enable **HTTP Basic** for the repo (Settings, or `MUNKI_REPO_BASIC_AUTH_*` env), clients authenticate to Munki Manager for catalogs, manifests, **and** icons on `/repo`. Munki sends the same `AdditionalHttpHeaders` to every host it talks to, so the `PackageURL` and `ClientResourceURL` targets will also receive that `Authorization: Basic` header. Either accept the same credentials there or make sure the host ignores stray `Authorization` headers.

---

## 4. Reverse proxy + static files (nginx on the Mac)

The Compose file publishes **only `frontend:3000`**. For production you usually put **nginx** (or Caddy) on the host listening on **80/443**:

- **Proxy** `/` → `http://127.0.0.1:3000` (frontend container).
- **Serve** `/pkgs/` from the directory above with `alias`. `/repo/icons/...` is served by the app from Postgres, so no nginx `alias` is needed for icons.

Example **nginx** server block (TLS certificates: use your own ACME/Let’s Encrypt or internal PKI; paths are illustrative):

```nginx
upstream munki_manager_ui {
    server 127.0.0.1:3000;
}

server {
    listen 443 ssl;
    server_name munki.example.com;

    ssl_certificate     /etc/nginx/ssl/example.crt;
    ssl_certificate_key /etc/nginx/ssl/example.key;

    location /pkgs/ {
        alias /var/munki-manager/munki-data/pkgs/;
        autoindex off;
    }

    location /client_resources/ {
        alias /var/munki-manager/munki-data/client_resources/;
        autoindex off;
    }

    # /repo/icons/... is served by the app from Postgres — no alias needed.

    location / {
        proxy_pass http://munki_manager_ui;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Install nginx with Homebrew (`brew install nginx`), place the config under `/opt/homebrew/etc/nginx/servers/` (or the Intel path), test with `nginx -t`, then `brew services start nginx`.

**Plain HTTP for a lab only:** listen on port 80 and omit `ssl_*`; use `http://` in all URLs below.

---

## 5. Configure `.env` for the Mac mini

Edit `.env` at the repo root (the backend loads it from there). At minimum:

| Variable | Example | Notes |
|----------|---------|--------|
| `SECRET_KEY` | output of `openssl rand -hex 32` | Required for JWT signing |
| `DATABASE_URL` | default in Compose is fine | `postgresql+asyncpg://automunki:automunki@db:5432/automunki` inside Compose |
| `MUNKI_REPO_PKG_BASE_URL` | `https://munki.example.com/pkgs` | Pins Munki's `PackageURL` in every enrolled profile. Must match whatever URL serves `pkgs/` (nginx `location /pkgs/`). Leave unset to manage via **Settings → Package & client resource URLs**. |
| `MUNKI_REPO_ICON_BASE_URL` | *(leave unset)* | Optional override — set to a CDN/bucket root only if you want to redirect `/repo/icons/*` off the app. Unset = serve from Postgres. |
| `MUNKI_REPO_CLIENT_RESOURCES_BASE_URL` | *(leave unset)* | Pins Munki's `ClientResourceURL`. When unset, derived from `MUNKI_REPO_PKG_BASE_URL` (swap trailing `/pkgs` for `/client_resources`). Set only if `client_resources/` live on a different host than `pkgs/`. Can also be managed from Settings. |
| `API_PUBLIC_URL` | `https://munki.example.com` | Public origin for callbacks (AutoPkg GitHub runner, etc.) |
| `CORS_ORIGINS` | `["https://munki.example.com"]` | JSON array; align with the URL users open in the browser |
| `AUTH_MODE` | `jwt` + `AUTH_REGISTRATION_OPEN=false` after first admin | Don’t leave open registration on a shared network |

**Optional:**

- `AUTOPKG_RUNNER_MODE=local` if you always run AutoPkg on this Mac (see [local runner](local-autopkg-runner.md)).
- `GITHUB_TOKEN` / `GITHUB_REPO` only if you use **GitHub Actions** for AutoPkg.

**Docker Compose** must pass the new variables into the **backend** service. Add to `docker-compose.yml` under `backend.environment` (or use a `docker-compose.override.yml`):

```yaml
      MUNKI_REPO_PKG_BASE_URL: ${MUNKI_REPO_PKG_BASE_URL:-}
      MUNKI_REPO_ICON_BASE_URL: ${MUNKI_REPO_ICON_BASE_URL:-}
      CORS_ORIGINS: ${CORS_ORIGINS:-'["http://localhost:3000"]'}
      API_PUBLIC_URL: ${API_PUBLIC_URL:-}
      AUTH_MODE: ${AUTH_MODE:-jwt}
      AUTH_REGISTRATION_OPEN: ${AUTH_REGISTRATION_OPEN:-false}
```

Adjust quoting for `CORS_ORIGINS` so the container receives a valid JSON array string.

---

## 6. Start the stack and run migrations

```bash
docker compose up -d
docker compose exec backend alembic upgrade head
```

Open **https://munki.example.com** (through nginx). API docs: **https://munki.example.com/api/docs**.

---

## 7. Munki client settings

On managed Macs, set the **repo** base URL to the path where catalogs are served (Next proxies `/repo` to the API):

- **`SoftwareRepoURL`** = `https://munki.example.com/repo`
  (no trailing slash; Munki will request `.../repo/catalogs/...` etc.)

For **reporting**, install the Swift **postflight** next to `managedsoftwareupdate` per [`agent/README.md`](../agent/README.md). It reads `SoftwareRepoURL` and POSTs to **`https://munki.example.com/api/v1/reports/checkin`** (same origin as the UI).

---

## 8. SMB sharing (optional, for admins)

Munki clients **do not** use SMB for `SoftwareRepoURL`. SMB is useful so admins **copy files** or **inspect** `pkgs/` from another Mac.

1. **System Settings → General → Sharing → File Sharing**
2. Add **`/var/munki-manager/munki-data`** (or a subfolder) with appropriate **read/write** users.
3. Use **SMB** for Mac/Windows clients on the LAN.

Keep **permissions** consistent with whatever user runs AutoPkg (often your admin account) so imports do not fail with “permission denied”.

---

## 9. AutoPkg on the same Mac mini

1. Install [AutoPkg](https://github.com/autopkg/autopkg/releases) and [Munki](https://github.com/munki/munki/releases) tools.
2. Point **`MUNKI_REPO`** at `/var/munki-manager/munki-data` (see `--setup-defaults` in [`docs/local-autopkg-runner.md`](./local-autopkg-runner.md)).
3. Set **`AUTOPKG_RUNNER_MODE=local`** and trigger runs from the UI as **Local Mac**. For **hands-off** execution, set **`LOCAL_RUNNER_TOKEN`** on the server (see [`docs/local-autopkg-runner.md`](./local-autopkg-runner.md)) and run **`AutoPkg/scripts/poll_local_autopkg.sh`** on the mini with the same token; otherwise use **`run_local_autopkg.sh`** with a JWT (`-t`) if required.

Imported pkginfo still needs to align with **Munki Manager’s** workflow (approval, promotion, etc.); see the main docs and API reference.

---

## 10. Remote access (optional)

- **Tailscale** or **VPN**: Expose the Mac mini only to trusted networks; do not expose Postgres (5432) or raw Docker ports to the internet.
- **Let’s Encrypt**: Use **DNS-01** or a small **HTTP-01** challenge on port 80 if the hostname is public.

---

## 11. Checklist

- [ ] Docker Compose healthy; `docker compose ps`
- [ ] `alembic upgrade head` applied
- [ ] `curl -I https://munki.example.com/repo/catalogs/<name>` returns 200 (after creating a catalog in the UI)
- [ ] A test file `https://munki.example.com/pkgs/...` is reachable (matches a pkginfo path)
- [ ] `MUNKI_REPO_PKG_BASE_URL` matches the nginx `location /pkgs/` path
- [ ] `curl -I https://munki.example.com/repo/icons/<some-uploaded-name>.png` returns 200 with an `ETag` header (served from Postgres)
- [ ] If upgrading from a disk-based icons setup, run `docker compose exec backend automunki ingest-icons /path/to/old/icons` once
- [ ] Client `SoftwareRepoURL` = `https://munki.example.com/repo`
- [ ] Postflight reports: `POST /api/v1/reports/checkin` returns 200 (check API logs or Reporting UI)

---

## Related docs

- [Deployment (general)](./deployment.md) — single-origin proxy, env vars, ngrok
- [Local AutoPkg runner](./local-autopkg-runner.md)
- [Architecture](./architecture.md)
- [API reference](./api-reference.md)
