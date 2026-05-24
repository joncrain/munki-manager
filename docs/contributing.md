# Contributing to Munki Manager

## Project Structure

```
munki-manager/
├── AutoPkg/              # Local AutoPkg runner workspace
│   ├── Overrides/        # Recipe overrides (rewritten by run_local_autopkg.sh from the API)
│   ├── Cache/            # AutoPkg processor cache
│   ├── Reports/          # Per-run AutoPkg report plists
│   └── scripts/          # run_local_autopkg.sh, poll_local_autopkg.sh,
│                         # write_overrides.py, save/load_metadata_cache.py,
│                         # report_results.py, read_env_value.py
├── backend/              # FastAPI Python backend
│   ├── alembic/          # Database migrations
│   ├── automunki/
│   │   ├── api/routes/   # API endpoint handlers (auth, autopkg, repo, …)
│   │   ├── models/       # SQLAlchemy ORM models
│   │   ├── schemas/      # Pydantic request/response schemas
│   │   ├── services/     # Business logic
│   │   ├── core/         # Config, DB, auth, RBAC middleware
│   │   ├── cli/          # `automunki` management commands
│   │   └── main.py       # FastAPI app + router wiring
│   └── tests/
├── frontend/             # React 19 SPA (Vite, served by nginx in prod)
│   └── src/
│       ├── app/          # Page components (mounted via React Router)
│       ├── components/   # Reusable components (shadcn/ui based)
│       ├── hooks/        # React hooks
│       ├── lib/          # API client, utilities
│       ├── router.tsx    # React Router routes
│       └── main.tsx      # SPA entry point
├── agent/                # Swift postflight for managed Macs (reporting)
│   ├── src/              # Swift sources
│   └── Makefile          # build / sign / install / pkg / package
├── terraform/            # Azure Container Apps + Postgres deployment
├── docs/                 # Documentation (start at docs/README.md)
├── icons/, pkgs/, pkgsinfo/   # Local Munki repo tree (used by AutoPkg local runner)
├── .github/workflows/    # checks.yml, autopkg_cloud_runner.yml, release-please.yml
├── Makefile              # Azure deploy helpers (tf-apply, deploy, migrate, …)
└── docker-compose.yml    # Local development stack (db + backend + frontend)
```

## Development Setup

### Backend

The backend uses [uv](https://docs.astral.sh/uv/) for environment management
(matches CI in [`.github/workflows/checks.yml`](../.github/workflows/checks.yml)).

```bash
cd backend
uv venv
uv pip install -e ".[dev]"

# Start just the database
docker compose up db -d

# Run migrations
uv run alembic upgrade head

# Optional: import an existing on-disk Munki repo (pkgsinfo/, manifests/,
# AutoPkg/Overrides/) into the database.
uv run automunki import-repo /path/to/munki-repo

# Start dev server
uv run uvicorn automunki.main:app --reload --port 8000
```

The `automunki` CLI also has `ingest-icons <dir> [--overwrite]` for backfilling
on-disk PNGs into the `software_icon` table.

### Frontend

```bash
cd frontend
bun install
bun dev
```

The Vite dev server starts on port 3000 and proxies `/api/*`, `/repo/*`, and
`/icons/*` to `BACKEND_URL` (default `http://localhost:8000`). See
[`vite.config.ts`](../frontend/vite.config.ts).

## Code Style

### Backend (Python)
- Use type hints everywhere
- Prefer `async def` for I/O operations
- Use Pydantic models for all API input/output
- Follow the FastAPI dependency injection pattern (see `automunki/api/deps.py`)
- Keep business logic in `services/`, not in route handlers
- Lint and format with `ruff` (`uv run ruff check` / `uv run ruff format`)

### Frontend (TypeScript)
- Use TypeScript strict mode
- Use TanStack Query for all API calls
- Use shadcn/ui components as the base
- Keep pages thin, extract logic into hooks
- Lint and format with [Biome](https://biomejs.dev/) (`bun run lint` /
  `bun run lint:fix`) — same checks CI runs.

## Adding a New API Endpoint

1. Add the SQLAlchemy model in `backend/automunki/models/`
2. Create Pydantic schemas in `backend/automunki/schemas/`
3. Add business logic in `backend/automunki/services/`
4. Create the route handler in `backend/automunki/api/routes/`
5. Register the router in `backend/automunki/main.py`
6. If the route should be reachable without a JWT (e.g. public health/repo
   endpoints), update `backend/automunki/core/rbac_middleware.py`
7. Create an Alembic migration: `uv run alembic revision --autogenerate -m "description"`
8. Add the TypeScript types and React Query hook to `frontend/src/lib/`
9. Build the frontend page/component and wire it into `frontend/src/router.tsx`

## Database Migrations

Always use Alembic for schema changes:

```bash
cd backend
uv run alembic revision --autogenerate -m "add new_field to munki_pkginfo"
uv run alembic upgrade head
```

Review auto-generated migrations before applying — they may need manual
adjustment for complex changes (enums, server defaults, JSON columns).

## Testing

```bash
cd backend
uv run pytest
```

CI runs the same `pytest` invocation against an ephemeral Postgres provided by
the workflow. See [`.github/workflows/checks.yml`](../.github/workflows/checks.yml).

## Releases

Releases are managed by [release-please](https://github.com/googleapis/release-please)
via `.github/workflows/release-please.yml` and `release-please-config.json`.
Use [Conventional Commits](https://www.conventionalcommits.org/) for messages
that should appear in the changelog.
