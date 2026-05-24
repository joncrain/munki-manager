# Munki Manager Deployment Guide

## Architecture

Munki Manager uses a **single-origin proxy** architecture. The frontend container (nginx) serves the Vite-built React SPA and proxies `/api/*`, `/repo/*`, and `/icons/*` requests to the FastAPI backend. Only **port 3000** needs to be exposed — the backend runs internally and is never accessed directly.

```
Browser / Munki client / Postflight agent / GitHub Actions
        │
        ▼
   Port 3000 (nginx)
        │
        ├── /              → React SPA (static files, history fallback to index.html)
        ├── /api/docs      → FastAPI Swagger docs (proxied)
        ├── /api/v1/*      → FastAPI backend (proxied to port 8000)
        ├── /repo/*        → Munki repo endpoints on the backend
        └── /icons/*       → rewritten to /api/v1/icons/* on the backend
```

The backend's top-level `/health`, `/ready`, and `/metrics` endpoints are **not** proxied through port 3000 — scrape them directly from inside the cluster, or add an explicit `location /health` block to [`frontend/nginx.conf.template`](../frontend/nginx.conf.template) if you want them publicly reachable.

This means:
- One URL for everything (UI, API, docs)
- One ngrok tunnel for external access: `ngrok http 3000`
- No CORS configuration needed
- GitHub Actions uses the same URL as the browser

## Prerequisites

- Docker and Docker Compose (recommended), **or**:
  - PostgreSQL 16
  - Python 3.12+ and [uv](https://docs.astral.sh/uv/)
  - Node.js 20+ / [Bun](https://bun.sh) 1.0+

## Quick Start with Docker Compose

```bash
git clone https://github.com/joncrain/munki-manager.git
cd munki-manager
cp .env.example .env
# Edit .env with your configuration (at minimum: SECRET_KEY, GITHUB_TOKEN, GITHUB_REPO)

docker compose up -d
docker compose exec backend alembic upgrade head
```

Access the application at **http://localhost:3000**:
- UI: http://localhost:3000
- API Docs: http://localhost:3000/api/docs
- Health Check (backend, via Docker): `docker compose exec backend curl -s localhost:8000/health`

### Exposing to the Internet (ngrok)

```bash
ngrok http 3000
```

Set `API_PUBLIC_URL` in your `.env` to the ngrok URL so GitHub Actions can call back:

```bash
API_PUBLIC_URL=https://xxxx.ngrok-free.app
```

Restart the backend to pick up the change, or pass it as an environment variable.

## Local Development (without Docker)

### Backend

```bash
cd backend
uv venv
uv pip install -e ".[dev]"

# Start PostgreSQL (or use Docker for just the DB)
docker compose up db -d

# Run migrations
uv run alembic upgrade head

# Start the server on port 8000
uv run uvicorn automunki.main:app --reload
```

### Frontend

```bash
cd frontend
bun install
bun dev
```

The Vite dev server starts on port 3000 and automatically proxies `/api/*` to `http://localhost:8000`. Open http://localhost:3000 — that's the only URL you need.

## Environment Variables

For **sign-in, registration, and the first administrator**, see **[users-and-auth.md](users-and-auth.md)**.

### Required

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string |
| `SECRET_KEY` | JWT signing secret (generate with `openssl rand -hex 32`) |

### GitHub Integration

| Variable | Description |
|----------|-------------|
| `GITHUB_TOKEN` | GitHub token for API access |
| `GITHUB_REPO` | Repository in `owner/repo` format |

### Proxy / Networking

| Variable | Description |
|----------|-------------|
| `API_PUBLIC_URL` | Public URL for GitHub Actions callbacks (e.g., your ngrok URL). Defaults to the first CORS origin. |
| `BACKEND_URL` | Where the frontend container proxies API requests (default: `http://localhost:8000`). Only change if the backend runs on a different host. In Docker Compose this is set to `http://backend:8000` automatically. |

### Object storage for the Munki repo

Packages, icons (when external), and `client_resources` zips are served from
whatever object store you point `MUNKI_REPO_PKG_BASE_URL` at — the backend
itself never serves package bytes. Supported and documented backends:

- **AWS S3 + CloudFront** — `STORAGE_BACKEND=s3`, set `AWS_*` and
  `CLOUDFRONT_DISTRIBUTION_ID`.
- **Azure Blob Storage (+ optional Front Door)** — `STORAGE_BACKEND=azure_blob`,
  set one of `AZURE_STORAGE_CONNECTION_STRING`, account-name + SAS token, or
  managed identity. See [Azure deployment](azure-deployment.md).
- **Mac mini nginx (self-hosted)** — set `MUNKI_REPO_PKG_BASE_URL` to the
  nginx URL; no `STORAGE_BACKEND` needed. See [Mac mini deployment](mac-mini-deployment.md).

See **[storage-backends.md](storage-backends.md)** for env-var reference and
swap instructions.

### Optional

| Variable | Description |
|----------|-------------|
| `DEBUG` | Enable debug mode (default: false) |
| `CORS_ORIGINS` | JSON array of allowed origins. Not needed when using the proxy. |
| `SLACK_WEBHOOK_URL` | Slack webhook for notifications |
| `LOCAL_RUNNER_TOKEN` | Shared secret for `poll_local_autopkg.sh` (Bearer token on claim + runner paths). See [local runner](local-autopkg-runner.md). |
| `SCHEDULER_ENABLED` | When `true` (default), the API runs a background loop every 60s to fire due AutoPkg schedules. Set `false` on all but one replica if you run multiple API processes. |
| `SCHEDULE_WEBHOOK_SECRET` | If set, `POST /api/v1/autopkg/schedules/run-due` with header `X-Schedule-Secret` runs the same “due schedules” logic (optional external cron, e.g. GitHub Actions). If empty, the endpoint returns 503. |

## Database Migrations

```bash
cd backend

# Create a new migration
uv run alembic revision --autogenerate -m "description"

# Apply migrations
uv run alembic upgrade head

# Rollback one migration
uv run alembic downgrade -1
```

## Client reporting (Swift postflight)

Fleet check-ins use the Swift **`postflight`** in [`agent/`](../agent/README.md): from `agent/`, run `make build` to produce `build/postflight` (universal binary), install it next to `managedsoftwareupdate` per Munki’s [preflight/postflight](https://github.com/munki/munki/wiki/Preflight-And-Postflight-Scripts) docs.

The binary reads Munki’s **`SoftwareRepoURL`** and POSTs to **`{origin}/api/v1/reports/checkin`** (scheme + host + port only; repo path stripped). That matches a single-origin deployment where the frontend container proxies `/api/*` to the backend—no separate `api_url` config or Python on the client.

## Cloud Deployment

For production, point `DATABASE_URL` at any managed Postgres 16+ provider — the asyncpg driver is required, e.g.:

```
postgresql+asyncpg://USER:PASSWORD@HOST:5432/DBNAME?sslmode=require
```

Providers that work out of the box: Azure Database for PostgreSQL Flexible Server (used by the included Terraform), Neon, Supabase, AWS RDS, Crunchy Bridge, etc.

### Hosting Options

Since only one port needs to be exposed, any platform that can run Docker works:

For a **self-hosted Mac mini** with packages on local disk and optional SMB for admins, see **[Mac mini deployment](mac-mini-deployment.md)** (nginx static `pkgs/`, `MUNKI_REPO_*` URLs, client `SoftwareRepoURL`). **Icons** are stored in Postgres (`software_icon` table) and served directly from `/repo/icons/<name>.png` — no nginx static alias required. Use `automunki ingest-icons <dir>` once to backfill an existing on-disk `icons/` directory. Set `MUNKI_REPO_ICON_BASE_URL` only if you want to redirect icons to an external CDN.

| Platform | Notes |
|----------|-------|
| **Azure Container Apps** | Terraform + manual deploy script in [`terraform/`](../terraform/), full guide in **[azure-deployment.md](azure-deployment.md)**. ~$20–35/mo with scale-to-zero. |
| **Railway** | `docker compose up` equivalent, free tier available, auto-deploy from GitHub |
| **Render** | Docker support, free tier for web services |
| **Fly.io** | Edge deployment, good for low-latency |
| **AWS Lightsail** | Cheapest AWS option, $3.50/mo for a container |
| **Any VPS** | DigitalOcean, Linode, Hetzner — just `docker compose up -d` |

Set `DATABASE_URL` to your Neon connection string and `API_PUBLIC_URL` to the public URL of the deployment.

## Production Considerations

- Use a strong `SECRET_KEY` (generate with `openssl rand -hex 32`)
- Only expose port 3000 — the backend should not be directly accessible
- Set `API_PUBLIC_URL` to your production URL so GitHub Actions callbacks work
- Configure log aggregation (the backend outputs structured JSON logs via `structlog`)
- Monitor the backend's `/health` and `/ready` endpoints (top-level on the backend container, **not** proxied through the frontend by default)
- Set up Prometheus scraping from the backend's `/metrics` (also top-level on the backend)
- Set `AUTH_MODE=jwt` (or `oidc`) and `AUTH_REGISTRATION_OPEN=false` once the first admin exists — see [users-and-auth.md](users-and-auth.md)
