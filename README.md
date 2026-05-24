# Munki Manager

Munki Manager is a **database-backed web application** for managing **Munki** catalogs, manifests, and pkginfo, together with **AutoPkg** recipe overrides, runs, and approvals. Munki clients continue to use standard HTTP repo URLs; the server compiles catalogs and manifests from PostgreSQL on demand.

This branch (`db-mode`) is the **full-stack product**: a React SPA, FastAPI API, RBAC, and Postgres — not a Git-only repo wrapper.

## Stack

| Layer | Technology |
|--------|------------|
| UI | React 19 + Vite + React Router, TanStack Query, shadcn/ui + Tailwind, served by nginx |
| API | FastAPI, SQLAlchemy 2 (async), Alembic migrations |
| Data | PostgreSQL 16+ |
| Auth | JWT (built-in via FastAPI Users) or OIDC; optional open registration; **page-level** read/write permissions for signed-in users |

## Features (high level)

- **Munki**: Software (pkginfo), catalogs, manifests (including conditional items and included manifests), on-demand plist compilation for clients
- **AutoPkg**: Recipe overrides, trust status, discover/import, run history, GitHub or local runner flows, approval queue
- **Reporting & audit**: Fleet check-ins, install history, audit log (where enabled)
- **Access control**: UI and API enforce **page keys** (e.g. software, manifests, catalogs, AutoPkg areas, admin). Users can have **read-only** access; mutating actions are hidden when they lack write permission

## Quick start

```bash
cp .env.example .env
# Set at least DATABASE_URL, SECRET_KEY, and (for AutoPkg/GitHub) GITHUB_TOKEN + GITHUB_REPO

docker compose up -d
docker compose exec backend alembic upgrade head
```

Open **http://localhost:3000** (the frontend container's nginx serves the React SPA and proxies `/api/*` and `/repo/*` to the API).

For detailed setup (local dev without Docker, ngrok, production, env vars), see **[docs/deployment.md](docs/deployment.md)**.

Full documentation index: **[docs/README.md](docs/README.md)**. Highlights:

- **[docs/architecture.md](docs/architecture.md)** — system design and data flow
- **[docs/users-and-auth.md](docs/users-and-auth.md)** — creating users, `AUTH_MODE`, registration, first admin
- **[docs/mac-mini-deployment.md](docs/mac-mini-deployment.md)** — Docker on a Mac mini, local `pkgs/` storage, nginx/SMB
- **[docs/azure-deployment.md](docs/azure-deployment.md)** — Azure Container Apps + Postgres Flexible Server via Terraform
- **[docs/client-onboarding.md](docs/client-onboarding.md)** — point a managed Mac at this server (self-service, `defaults write`, or MDM)
- **[docs/contributing.md](docs/contributing.md)** — repo layout and dev workflow

## Repository layout

```
munki-manager/
├── backend/          # FastAPI app, models, Alembic migrations, tests
├── frontend/         # React SPA (Vite + nginx)
├── agent/            # Swift postflight for managed Macs (reporting)
├── AutoPkg/          # Local AutoPkg runner scripts + Overrides/Cache/Reports
├── terraform/        # Azure Container Apps deployment
├── docs/             # Deployment, architecture, contributing, runners
├── Makefile          # Azure deploy helpers (tf-apply, deploy, migrate, …)
└── docker-compose.yml
```

## GitHub Actions

Workflows under `.github/workflows/`:

- **`autopkg_cloud_runner.yml`** — `workflow_dispatch` AutoPkg runs that report
  back to the API via `API_PUBLIC_URL` (see [`docs/local-autopkg-runner.md`](docs/local-autopkg-runner.md) for the local-runner alternative).
- **`checks.yml`** — frontend (`bun run lint` + `bun run build`) and backend
  (ruff + pytest) checks on every PR.
- **`release-please.yml`** — automated release PRs.

## Demo site

https://munki-manager.joncra.in
