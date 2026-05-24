# Munki Manager docs

Start here. The top-level [`README.md`](../README.md) has the 60-second pitch
and the quick-start; everything else is in this directory.

## By task

### "I want to deploy this somewhere."

| Path | When to read |
|------|--------------|
| **[deployment.md](deployment.md)** | Generic deployment guide \u2014 single-origin proxy, env vars, ngrok for local-public testing, picking a Postgres provider. **Read this first.** |
| **[mac-mini-deployment.md](mac-mini-deployment.md)** | Self-hosted on a Mac mini with Docker + nginx + local `pkgs/`, optional SMB for admins. Lowest cost, single host. |
| **[azure-deployment.md](azure-deployment.md)** | Azure Container Apps + Postgres Flexible Server via the Terraform in [`terraform/`](../terraform/) and the `make tf-apply` / `make deploy` flow. ~$20\u201335/mo. |
| **[storage-backends.md](storage-backends.md)** | Where the actual `.pkg` bytes live. AWS S3+CloudFront, Azure Blob (+ optional Front Door), or Mac mini nginx \u2014 swap-in / swap-out instructions. |

### "I need to onboard Macs / users."

| Path | When to read |
|------|--------------|
| **[client-onboarding.md](client-onboarding.md)** | Pointing a managed Mac at this server: self-service token flow (recommended), `defaults write`, or MDM-pushed `.mobileconfig`. Also covers the optional Swift postflight from [`agent/`](../agent/README.md) for Reporting. |
| **[users-and-auth.md](users-and-auth.md)** | `AUTH_MODE` (`disabled` / `jwt` / `oidc`), `AUTH_REGISTRATION_OPEN`, bootstrapping the first admin (`UPDATE "user" SET is_superuser = true`), and how RBAC pages work. |
| **[google-workspace-sso.md](google-workspace-sso.md)** | Workspace SAML reference (general), with notes on why Munki Manager itself uses **OIDC** (not SAML) for built-in SSO. |

### "I want to integrate with the API or run AutoPkg locally."

| Path | When to read |
|------|--------------|
| **[api-reference.md](api-reference.md)** | Endpoint overview \u2014 auth, RBAC, `/repo`, AutoPkg, Reporting, Settings. Full schemas live in Swagger at `/api/docs`. |
| **[local-autopkg-runner.md](local-autopkg-runner.md)** | Running AutoPkg on a Mac you control instead of GitHub Actions: one-shot `run_local_autopkg.sh`, the unattended `poll_local_autopkg.sh` daemon, and `LOCAL_RUNNER_TOKEN`. |

### "I want to understand or change the codebase."

| Path | When to read |
|------|--------------|
| **[architecture.md](architecture.md)** | System architecture, data flow, database schema (Munki + AutoPkg + Reporting + RBAC), tech stack. |
| **[contributing.md](contributing.md)** | Repo layout, dev setup (uv for backend, bun for frontend), how to add an endpoint, migrations, tests, lint. |

## Conventions

- Filenames are kebab-case `.md`.
- Cross-links between docs use **relative** paths (e.g. `./mac-mini-deployment.md`)
  so they work both on GitHub and in any local Markdown viewer.
- When a doc references a path in the repo, it links the actual file (e.g.
  [`Makefile`](../Makefile), [`backend/automunki/core/config.py`](../backend/automunki/core/config.py)).
