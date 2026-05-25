# Local AutoPkg runner

Munki Manager can trigger AutoPkg in **GitHub Actions** (default) or register a run for a **Mac you control** (local runner). Local runs do not call the GitHub API; you execute the same steps the [`autopkg_cloud_runner.yml`](../.github/workflows/autopkg_cloud_runner.yml) workflow runs, pointed at your Munki Manager API.

## Prerequisites

- Autopkg installed
- Autopkg configured:

```sh
defaults write com.github.autopkg CACHE_DIR /path/to/AutoPkg/Cache
defaults write com.github.autopkg MUNKI_REPO /path/to/munki-repo
```


## Quick start (script)

From your munki-manager clone, after you trigger **Local Mac** in the UI and copy the run UUID.

**Easiest (JWT or OIDC on the API):** put the same **`LOCAL_RUNNER_TOKEN`** in the **repo root `.env`** as on the server (the value the backend already loads). `run_local_autopkg.sh` and `poll_local_autopkg.sh` read it automatically—no `export` before each run. Then:

```bash
./AutoPkg/scripts/run_local_autopkg.sh \
  --backend-url "https://your-api.example.com" \
  --run-id "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
```

**Overrides:** set `AUTOMUNKI_API_TOKEN`, pass `--token`, or use a user **JWT** in `localStorage` (`token`) if you are not using the shared runner secret.

**Troubleshooting 401:** The bearer value must match the server’s `LOCAL_RUNNER_TOKEN` exactly (what the API loaded from its own `.env`). Resolution order is: `--token`, then `LOCAL_RUNNER_TOKEN` in **repo** `${WORKSPACE}/.env`, then `AUTOMUNKI_API_TOKEN`. If it still fails: confirm the line is `LOCAL_RUNNER_TOKEN=...` (with or without a leading `export`); pass `-w /path/to/munki-manager` if the script’s default workspace is not your clone (so it finds the right `.env`); ensure the backend was restarted after changing `LOCAL_RUNNER_TOKEN` on the server. Check whether the **running** process has a token: `curl -sS http://localhost:8000/health` (or your API origin) — `local_runner_configured` must be `true` or the server will reject the runner secret.

When **`AUTH_MODE=disabled`**, the script can call those endpoints without a token (no `LOCAL_RUNNER_TOKEN` needed).

Optional arguments:

| Flag | Meaning |
|------|---------|
| `-w`, `--workspace` | Path to repo root (default: inferred from script location) |
| `--recipes` | Comma-separated recipe names (same as UI subset) |
| `-t`, `--token` | JWT if your API requires `Authorization: Bearer` (also sets `AUTOMUNKI_API_TOKEN` for Python) |
| `--keep-temps` | Keep run scratch files (see below); default is to delete them when the script exits |
| `--autopkg-force` | Run **`autopkg run --force`** for each recipe instead of `cloud-autopkg-runner` (see troubleshooting) |
| `--reset` | Make AutoPkg "forget" prior local runs: empties `WORKSPACE/AutoPkg/Cache`, `WORKSPACE/pkgsinfo`, `WORKSPACE/pkgs`, and skips the server metadata cache fetch (uses an empty cache instead). Forces re-download + re-import (see troubleshooting). |

By default, the script **removes temporary files** when it finishes (success or failure): `metadata_cache_response.json`, `metadata_cache.json`, `run_config.json`, `autopkg_runner.log`, `AutoPkg/run_recipe_list.json`, `AutoPkg/run_repo_list.txt`, and `AutoPkg/Reports/*.plist`. Override plists under `AutoPkg/Overrides/` are **not** deleted (they are rewritten from the API on the next run). Use `--keep-temps` to debug a failed run.

One-time AutoPkg `defaults` on this Mac:

```bash
./AutoPkg/scripts/run_local_autopkg.sh --setup-defaults
# optional: pass a GitHub token for recipes that use the GitHub processor
./AutoPkg/scripts/run_local_autopkg.sh --setup-defaults --github-token "ghp_..."
```

Use `-w` with `--setup-defaults` if the repo is not next to the default path.

Full reference: `./AutoPkg/scripts/run_local_autopkg.sh --help`

## Automated daemon (no manual command)

If you set **`LOCAL_RUNNER_TOKEN`** on the Munki Manager server (same value in `.env` as `openssl rand -hex 32`), the API accepts that token as `Authorization: Bearer …` for the local runner endpoints (claim, metadata cache, run config). A Mac that runs AutoPkg can then loop with **`poll_local_autopkg.sh`**, which:

1. `POST /api/v1/autopkg/runs/claim-next-local` — if **204**, nothing is queued; wait and retry.
2. If **200**, read `id` from the JSON body and invoke `run_local_autopkg.sh` with `--run-id` (same token for curl/Python).

**Server**

```bash
# In the repo root .env (or Docker env for `backend`)
LOCAL_RUNNER_TOKEN=<long-random-secret>
```

Restart the backend. The token is accepted for the local-runner paths in [API reference](api-reference.md), including **`POST /autopkg/pkginfo/ingest`** and **`POST /autopkg/icons/ingest`** (so you can lock down those ingests with Bearer when not relying on a private network).

### Icons after import

When **Extract icon (MunkiImporter)** is enabled on a recipe, AutoPkg writes a PNG under the Munki repo’s `icons/` directory (same root as `pkgs/` / `pkgsinfo/`). In Munki Manager this is the **Extract icon (MunkiImporter)** switch on the recipe: it makes the override plist set `Input.extract_icon` for the runner. The AutoPkg `MunkiImporter` processor **only** runs icon extraction when that key is true (unlike the interactive **`munkiimport` CLI**, which can prompt to create a product icon even when you did not pass `--extract-icon`).

**AutoPkg follows `defaults read com.github.autopkg MUNKI_REPO`**, not necessarily your shell’s `export MUNKI_REPO` or `GITHUB_WORKSPACE`. The `report_results.py` step resolves that path **first** (then env, then workspace) so it reads `icons/` and `pkgsinfo/` from the same tree MunkiImporter used. `munkiimport` output like `Imported icons/Foo.png` means **`$MUNKI_REPO/icons/Foo.png`** for whatever repo `munkiimport` was using (confirm with `defaults read com.github.autopkg MUNKI_REPO` on the Mac).

**Runner Mac**

```bash
export AUTOMUNKI_BACKEND_URL=https://munki-manager.example.com
export LOCAL_RUNNER_TOKEN=<same-as-server>
./AutoPkg/scripts/poll_local_autopkg.sh --backend-url "$AUTOMUNKI_BACKEND_URL" --token "$LOCAL_RUNNER_TOKEN"
```

Optional: `--workspace /path/to/munki-manager`, `--interval 30` (seconds between polls when idle).

**UI:** In the AutoPkg run dialog, choose **Local Mac (automated daemon)** so the success toast does not expect you to copy a shell command. **Local Mac (copy shell command)** keeps the previous behavior.

**launchd (stay running after login)**

Use a LaunchAgent that sets `AUTOMUNKI_BACKEND_URL` and `LOCAL_RUNNER_TOKEN` (or read the token from Keychain with `security find-generic-password -s munki-manager-local-runner -w`). Run `poll_local_autopkg.sh` with `RunAtLoad` and `KeepAlive`.

**Note:** You can still use a normal **user JWT** with `run_local_autopkg.sh` instead of `LOCAL_RUNNER_TOKEN`; the daemon path is for machines that should not store a user password.

## When to use a local runner

- You want builds on an internal Mac without GitHub-hosted minutes or workflow limits.
- Recipes need resources or network access that CI cannot provide.
- You are developing or debugging AutoPkg and want a tight loop on one machine.

`uv` / `uvx` in CI only isolates the **cloud-autopkg-runner** Python tool. It does not sandbox AutoPkg itself; a local runner still needs **AutoPkg** and **Munki tools** installed on that Mac (see below).

## UI: GitHub vs local

1. Open **Settings** — the server default is shown (`AUTOPKG_RUNNER_MODE` in `.env`).
2. On **AutoPkg → Runs** (or the recipe quick-run dialog), choose **Runner**:
   - **GitHub Actions**
   - **Local Mac (copy shell command)** — toast shows `./AutoPkg/scripts/run_local_autopkg.sh …`
   - **Local Mac (automated daemon)** — for `poll_local_autopkg.sh` + `LOCAL_RUNNER_TOKEN`; no command to copy
3. Your choice is remembered in the browser for the next trigger.

- **GitHub Actions**: the API creates an `autopkg_run` and dispatches `autopkg_cloud_runner.yml` (requires `GITHUB_TOKEN` and `GITHUB_REPO` on the server).
- **Local Mac** (both variants): the API creates an `autopkg_run` with status **pending** and `runner_type` **local**. Either run **`poll_local_autopkg.sh`** (automated) or **`run_local_autopkg.sh`** with the run `id` (manual), or follow [manual steps](#manual-steps-same-as-the-script) below.

## Prerequisites on the local Mac

| Requirement | Purpose |
|-------------|---------|
| macOS | AutoPkg and most processors assume a Mac. |
| [AutoPkg](https://github.com/autopkg/autopkg/releases) | `autopkg` CLI. |
| [Munki](https://github.com/munki/munki/releases) | MunkiImporter / `makepkginfo` for `.munki.recipe` flows. |
| [uv](https://docs.astral.sh/uv/) | Used to run `uvx cloud-autopkg-runner` (same as CI). |
| Git | `autopkg repo-add` clones recipe repos. |
| Clone of this repo | Contains `AutoPkg/scripts/` and layout expected by scripts. |

The Munki Manager **API** must be reachable from that Mac (same URL as `API_PUBLIC_URL` / your tunnel).

## Manual steps (same as the script)

The script [`AutoPkg/scripts/run_local_autopkg.sh`](../AutoPkg/scripts/run_local_autopkg.sh) automates the following. Use this section only if you need to run pieces by hand.

### One-time AutoPkg preferences

Equivalent to `./AutoPkg/scripts/run_local_autopkg.sh --setup-defaults` (and optional `--github-token`):

```bash
export GITHUB_WORKSPACE="/path/to/munki-manager"
mkdir -p "$GITHUB_WORKSPACE/pkgs" "$GITHUB_WORKSPACE/AutoPkg/Overrides" \
  "$GITHUB_WORKSPACE/AutoPkg/repos" "$GITHUB_WORKSPACE/AutoPkg/Reports" \
  "$GITHUB_WORKSPACE/AutoPkg/Cache" "$HOME/Library/AutoPkg"

defaults write com.github.autopkg CACHE_DIR "$GITHUB_WORKSPACE/AutoPkg/Cache"
defaults write com.github.autopkg RECIPE_OVERRIDE_DIRS "$GITHUB_WORKSPACE/AutoPkg/Overrides/"
defaults write com.github.autopkg RECIPE_REPO_DIR "$GITHUB_WORKSPACE/AutoPkg/repos/"
defaults write com.github.autopkg FAIL_RECIPES_WITHOUT_TRUST_INFO -bool TRUE
defaults write com.github.autopkg MUNKI_REPO "$GITHUB_WORKSPACE"
# Optional: for recipes that use the GitHub processor
defaults write com.github.autopkg GITHUB_TOKEN "ghp_..."
```

### Run pipeline (after a local run is registered)

Set `GITHUB_WORKSPACE`, `BACKEND_URL` (no `/api/v1`), `RUN_ID`, and optionally `RECIPE_FILTER`, then run the same blocks as in the script: metadata cache → `runs/config` + `write_overrides.py` → `autopkg repo-add` / `repo-update` → `uvx cloud-autopkg-runner` → `save_metadata_cache.py` → `report_results.py` per plist → `POST .../complete`.

**Recipe targeting:** A run created for one (or a few) recipes stores that in **`recipe_filter`**. The script [`run_local_autopkg.sh`](../AutoPkg/scripts/run_local_autopkg.sh) now reads `GET /autopkg/runs/{RUN_ID}` and passes those names to `GET /autopkg/runs/config?recipes=…` so only those overrides and their GitHub repos are materialized. Without that, `config` with no `recipes` query returns **every** enabled override — which is why a “single recipe” run could look like a full import on the Mac. You can still override with `--recipes` or a manual `?recipes=` when calling the API.

## Troubleshooting

- **`no_change` / “not newer” when the recipe was previously run on this Mac** (typical when you run a recipe locally, then deploy a different Munki Manager and run the same recipe against it): three things on disk can short-circuit AutoPkg, and you usually have to clear all three together:
  1. `MUNKI_REPO/pkgsinfo/<App>/...pkginfo` — **MunkiImporter** sees the version is already in the munki repo and reports `no_change`.
  2. `CACHE_DIR/<RecipeID>/` — receipts and the previously downloaded artifact let earlier processors skip work.
  3. `metadata_cache.json` (fetched from `/api/v1/autopkg/metadata-cache`) — `cloud-autopkg-runner` uses it to fake the download so URLDownloader returns `download_changed=False`.

  **Important:** "MUNKI_REPO" and "CACHE_DIR" above are AutoPkg's own preferences (`defaults read com.github.autopkg MUNKI_REPO` / `CACHE_DIR`), not necessarily a directory under the workspace. `run_local_autopkg.sh` now **always realigns these to the workspace** at the top of every run and prints the resolved paths (look for `==> AutoPkg paths in effect ...` in the output) so you can spot drift immediately. If you previously ran AutoPkg against a different project, the first invocation of the script will rewrite those keys.

  **Fix (pick one):**
  1. **`--reset`** on `run_local_autopkg.sh`: empties all three at once (the resolved `pkgsinfo/`, `pkgs/`, and `CACHE_DIR/` trees — using `defaults read`, so it is correct even if AutoPkg points outside the workspace — plus uses an empty metadata cache for this run). Repos and overrides are kept. This is the closest you can get to "first run on this Mac."
  2. **`--autopkg-force`**: bypasses `cloud-autopkg-runner` and runs `autopkg run <recipe> --force` per recipe (AutoPkg 2.3+). Forces a re-download even if `pkgsinfo/` still has the old plist; combine with `--reset` for a fully clean re-import.
  3. **Manual**: `rm -rf $(defaults read com.github.autopkg CACHE_DIR) $(defaults read com.github.autopkg MUNKI_REPO)/pkgsinfo $(defaults read com.github.autopkg MUNKI_REPO)/pkgs` and either delete `metadata_cache.json` before the run or use `--reset`.
- **DB metadata cache (optional)**: To clear the **server-side** cache for a specific recipe across all runners: `DELETE /api/v1/autopkg/metadata-cache?recipe_key=AdobeReader.munki.recipe` (see [API reference](api-reference.md)). Keys match override filenames like `AdobeReader.munki.recipe`. `--reset` only bypasses the cache for the current local run; it does not clear the server entry.

- **`FileNotFoundError` / `PermissionError` on a path from another runner** (`/Users/runner/work/...` on a Mac mini, or `/opt/UnitySrc/...` on a GitHub-hosted runner): The metadata cache `file_path` entries are absolute paths under the **previous** runner's workspace, and `cloud-autopkg-runner` tries to `stat` them on the new one. The fix is layered:
  - **Server (current):** `PUT /metadata-cache` rewrites `<workspace>/AutoPkg/Cache/...` to a `${WORKSPACE}/AutoPkg/Cache/...` placeholder. New uploads are runner-portable by construction.
  - **Client (current):** [`load_metadata_cache.py`](../AutoPkg/scripts/load_metadata_cache.py) expands the placeholder back to the local `GITHUB_WORKSPACE`, *and* rescues legacy entries that still have raw absolute paths by replacing everything before `/AutoPkg/Cache/` with the local workspace.
  - **If you still see it**, your cache row was written before this fix landed. Either run the same recipe again (the runner saves a clean entry on the way out), or clear the entry: `DELETE /api/v1/autopkg/metadata-cache?recipe_key=<RecipeName>.munki.recipe`. When invoking the loader by hand, run from the repo root with `export GITHUB_WORKSPACE="$(pwd)"`; [`run_local_autopkg.sh`](../AutoPkg/scripts/run_local_autopkg.sh) handles this for you.
- **`Could not find parent recipe for com.github.<author>.<NameXYZ>`**: AutoPkg failed to resolve a `ParentRecipe` because the `autopkg repo-add` list passed to the runner was incomplete. Munki Manager builds that list from each recipe's stored `trust_info.parent_recipes`, and if the trust chain was *partially* recorded (e.g. when the GitHub PAT used to import the recipe couldn't read part of the chain — the historical fine-grained-PAT-vs-`autopkg/*` issue), the missing repo never makes it into `run_repo_list.txt`. Fix: from **Recipe Management → Verify Trust** (or `POST /api/v1/autopkg/recipes/{id}/verify-trust`) re-walk the chain with the current PAT, then trigger a new run. The repo list will include the canonical `autopkg/recipes` (and any other parent author repo) and resolution succeeds.
- **`401` / auth errors**: pass `-t` / `--token` (or `AUTOMUNKI_API_TOKEN`) so curl and Python requests send a Bearer token.
- **Trust blocked recipes**: the API omits them from `/runs/config` until trust is verified — same as GitHub Actions.
- **MUNKI_REPO**: must be writable; recipes import pkginfo under `pkgsinfo/` relative to that repo path.

## Environment reference

| Variable | Meaning |
|----------|---------|
| `AUTOPKG_RUNNER_MODE` | Server default: `github` or `local` (when the UI does not send `runner`). |
| `API_PUBLIC_URL` | Used when dispatching GitHub Actions so the workflow can call back to your API. |
| `GITHUB_TOKEN` / `GITHUB_REPO` | Required on the **server** only for **GitHub** runner mode. |
| `AUTOMUNKI_API_TOKEN` | Optional; same as `--token` for local script Python `urllib` calls. |
| `LOCAL_RUNNER_TOKEN` | **Server:** shared secret so the daemon can authenticate without a user JWT. **Client:** same value in `Authorization: Bearer` for `poll_local_autopkg.sh` / `run_local_autopkg.sh` when not using a JWT. |
