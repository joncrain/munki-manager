# Munki Manager Architecture

## Overview

Munki Manager is a web-based management platform for Munki and AutoPkg. It replaces the traditional Git-based workflow with a database-backed web application while maintaining compatibility with existing Munki clients through **HTTP endpoints** that compile catalogs and manifests from the database on demand.

## System Architecture

```
┌───────────────────────────────────────────────────────────────┐
│                        Mac Fleet                              │
│  ┌──────────────┐  ┌─────────────────┐                        │
│  │ Munki Client │  │ Munki Manager agent │                    │
│  └──────┬───────┘  └───────┬─────────┘                        │
└─────────┼──────────────────┼──────────────────────────────────┘
          │                  │
          ▼                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Docker Compose / Host                        │
│  ┌──────────────┐  ┌─────────────────────────────────────────┐  │
│  │ Vite SPA +   │  │ FastAPI (:8000)                         │  │
│  │ nginx :3000  │──│ REST API, plist compilation, `/repo/*`  │  │
│  └──────────────┘  └──────────────────┬──────────────────────┘  │
│                                       │                         │
│                            ┌──────────▼───────────┐             │
│                            │ PostgreSQL 16        │             │
│                            │  - Munki data model  │             │
│                            │  - AutoPkg tracking  │             │
│                            │  - Fleet inventory   │             │
│                            │  - Audit trail       │             │
│                            └──────────────────────┘             │
└─────────────────────────────────────────────────────────────────┘
          ▲
          │ workflow_dispatch
┌─────────┴──────────────────┐
│ GitHub Actions             │
│  - AutoPkg macOS Runner    │
└────────────────────────────┘
```

## Data Flow

### AutoPkg Run Flow

1. User triggers run from UI or schedule fires
2. Backend creates `autopkg_run` with `runner_type` **github** or **local**
3. **GitHub**: API dispatches `autopkg_cloud_runner.yml`. **Local**: no GitHub call — status stays **pending** until someone runs AutoPkg on a Mac using [local runner](local-autopkg-runner.md) steps
4. macOS runner (Actions or your machine) runs AutoPkg / `cloud-autopkg-runner`
5. For each imported item, the runner POSTs `/api/v1/autopkg/pkginfo/ingest` (merged with the stored override) then `/api/v1/autopkg/runs/{id}/results`
6. Backend stores pkginfo and per-recipe results. For an **override** with **auto_promote** off, ingest assigns the pkginfo only to the catalog marked **quarantine** (`munki_catalog.is_quarantine`) and records the override’s intended catalog list on `munki_pkginfo.pending_catalog_names` until an operator approves on **Approvals** (then catalogs are applied and pending is cleared). Trust failures still surface as pending approval on the same queue.
7. Runner calls `/api/v1/autopkg/runs/{id}/complete` when done

Scheduled **promotion channels** (`munki_promotion_channel` + steps) move pkginfo between catalogs after **dwell** time in each source catalog (`munki_pkginfo_catalog.entered_at`). The scheduler loop and the `/api/v1/autopkg/schedules/run-due` webhook also run legacy auto-time rules plus the channel tick.

### Catalog delivery

Munki catalog and manifest plists are compiled **on demand** when clients request them via the repo HTTP routes (backed by the database). Optional: `POST /api/v1/catalogs/makecatalogs` audits all catalogs and returns warnings (empty catalogs, missing installer paths, plist sizes).

### Client Reporting Flow

1. The Swift **postflight** in [`agent/`](../agent/README.md) is installed next to `managedsoftwareupdate` per Munki's [preflight/postflight](https://github.com/munki/munki/wiki/Preflight-And-Postflight-Scripts) docs and runs after every `managedsoftwareupdate` invocation
2. It reads Munki's `SoftwareRepoURL`, derives `{origin}/api/v1/reports/checkin`, and POSTs hardware info, installed software, and Munki install results
3. Backend upserts `client_machine`, appends a row to `client_machine_checkin`, and replaces `client_install_report` rows for that check-in
4. **Reporting** (UI) lists devices, compliance, install history, and per-device 90-day check-in sparklines
5. `POST /reports/checkin` is intentionally **unauthenticated** (serial number is the key); restrict it with a reverse proxy / mTLS if needed

## Database Schema

### Core Munki Entities

- **munki_pkginfo** - Software package metadata (name, version, installer details, scripts); optional **pending_catalog_names** for quarantined imports awaiting approval
- **munki_catalog** - Named catalogs (test, production, etc.); optional **is_production** and **is_quarantine** flags (exactly one quarantine catalog is enforced in the API when the flag is set)
- **munki_pkginfo_catalog** - Many-to-many: which packages are in which catalogs; **entered_at** supports promotion dwell time
- **munki_promotion_channel** / **munki_promotion_channel_step** - Named promotion flows (e.g. slow/fast) with ordered source→target catalog steps and dwell days
- **app_workflow_preferences** - Singleton row for defaults such as **default_promotion_channel_id**
- **munki_manifest** - Munki manifests defining what machines get
- **munki_manifest_item** - Items within manifests (managed_installs, optional_installs, etc.)
- **munki_manifest_catalog** - Which catalogs a manifest searches
- **munki_manifest_inclusion** - Manifest hierarchy (included_manifests)
- **munki_promotion_rule** - Per-title promotion configuration

### AutoPkg Entities

- **autopkg_recipe** - Recipe overrides and configuration (optional `source_repo_full_name` = GitHub `owner/repo`); optional **promotion_channel_id** for timed catalog promotion
- **autopkg_schedule** - Cron expression + timezone + optional recipe subset + runner (`github` or `local`); drives scheduled runs
- **autopkg_run** - Run history with status tracking (optional `schedule_id` when created from a schedule)
- **autopkg_run_result** - Per-recipe results with approval workflow
- **autopkg_trust_change_request** - Pending trust updates for recipes
- **github_recipe_repo** - Cached GitHub repos for Discover (autopkg org + optional `is_custom` repos)
- **github_recipe** - Cached `.munki.recipe` paths per repo

### Supporting Entities

- **user** - Auth via FastAPI-Users with role field
- **audit_log** - Full compliance audit trail with before/after snapshots
- **client_machine** - Fleet inventory from agent check-ins
- **client_install_report** - Per-machine install status

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI + Python 3.12 |
| ORM | SQLAlchemy 2.0 (async) |
| Migrations | Alembic |
| Database | PostgreSQL 16 |
| Auth | FastAPI Users (JWT, OIDC bridge) |
| Frontend | React 19 + Vite (built with Bun), served by nginx |
| Routing | React Router |
| UI Components | shadcn/ui + Tailwind CSS |
| Data Tables | TanStack Table |
| Data Fetching | TanStack Query |
| Containers | Docker Compose (dev), Azure Container Apps (prod) |
| CI/CD | GitHub Actions |
| Object storage (pkgs) | Pluggable: AWS S3 + CloudFront, Azure Blob (+ optional Front Door), or Mac mini nginx — see [`storage-backends.md`](storage-backends.md) |
| Observability | structlog + Prometheus (`/metrics` on the backend) |
