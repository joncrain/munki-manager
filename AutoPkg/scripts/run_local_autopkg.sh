#!/usr/bin/env zsh
# Local AutoPkg runner — same steps as docs/local-autopkg-runner.md and
# .github/workflows/autopkg_cloud_runner.yml
#
# Examples:
#   ./AutoPkg/scripts/run_local_autopkg.sh --backend-url https://app.example.com --run-id <uuid>
#   ./AutoPkg/scripts/run_local_autopkg.sh -b http://localhost:8000 -r <uuid> -w ~/src/munki-manager --recipes Firefox
#   (Use :8000 for FastAPI directly; :3000 is Vite and only proxies /api when the dev server runs.)
#   ./AutoPkg/scripts/run_local_autopkg.sh -b http://localhost:8000 -r <uuid> --autopkg-force   # autopkg run --force
#   ./AutoPkg/scripts/run_local_autopkg.sh --setup-defaults
#   ./AutoPkg/scripts/run_local_autopkg.sh --setup-defaults --github-token ghp_xxx
# Fully automated (claim pending runs — see docs/local-autopkg-runner.md):
#   ./AutoPkg/scripts/poll_local_autopkg.sh -b https://app.example.com -t "$LOCAL_RUNNER_TOKEN"

set -euo pipefail

SCRIPT_PATH="${0:A}"
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
DEFAULT_WORKSPACE="$(cd "$SCRIPT_DIR/../.." && pwd)"

usage() {
  cat <<'EOF'
Usage: run_local_autopkg.sh --backend-url URL --run-id UUID [options]

  Run the full local pipeline after you trigger a "Local Mac" run in Munki Manager.

Required:
  -b, --backend-url URL   API origin (no /api/v1), e.g. http://localhost:8000 for local FastAPI.
                          (http://localhost:3000 = Vite only; use :8000 unless you rely on the proxy.)
  -r, --run-id UUID       autopkg_run id from the Runs UI or API.

Optional:
  -w, --workspace PATH    munki-manager repo root (default: directory above AutoPkg/scripts)
      --recipes LIST      Comma-separated recipe override names; overrides the run's stored
                          recipe filter. If you omit this, the script loads the filter from
                          GET /autopkg/runs/<run-id> (the same set the UI used when the run
                          was created) so a single-recipe run does not fetch every override.
  -t, --token TOKEN       Bearer: override LOCAL_RUNNER_TOKEN from .env / AUTOMUNKI_API_TOKEN
      --keep-temps        Do not delete run scratch files (metadata cache, run_config, logs, reports)
      --autopkg-force     Run ``autopkg run`` per recipe instead of cloud-autopkg-runner (re-import / stuck no_change).
                          Adds ``--force`` when your ``autopkg`` build supports it (AutoPkg 2.3+); older builds run without it.
      --reset             Make AutoPkg "forget" prior local runs: empty WORKSPACE/AutoPkg/Cache,
                          WORKSPACE/pkgsinfo, WORKSPACE/pkgs, and skip the server metadata cache
                          fetch (use an empty cache instead). Forces re-download + re-import.

One-time AutoPkg defaults (macOS):
      --setup-defaults    Only create dirs and run defaults write; then exit
      --github-token T    With --setup-defaults: set com.github.autopkg GITHUB_TOKEN (optional)

  -h, --help              Show this help

Environment (optional):
  AUTOMUNKI_API_TOKEN     Same as --token; passed to Python urllib calls
  (no env needed if WORKSPACE/.env contains LOCAL_RUNNER_TOKEN — same value as the server)

EOF
}

BACKEND_URL=""
RUN_ID=""
WORKSPACE="$DEFAULT_WORKSPACE"
RECIPE_FILTER=""
TOKEN=""
SETUP_DEFAULTS_ONLY=0
GITHUB_TOKEN_FOR_DEFAULTS=""
KEEP_TEMPS=0
AUTOPKG_FORCE=0
RESET=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    -b|--backend-url)
      BACKEND_URL="${2:?}"
      shift 2
      ;;
    -r|--run-id)
      RUN_ID="${2:?}"
      shift 2
      ;;
    -w|--workspace)
      WORKSPACE="${2:?}"
      shift 2
      ;;
    --recipes)
      RECIPE_FILTER="${2:?}"
      shift 2
      ;;
    -t|--token)
      TOKEN="${2:?}"
      shift 2
      ;;
    --setup-defaults)
      SETUP_DEFAULTS_ONLY=1
      shift
      ;;
    --github-token)
      GITHUB_TOKEN_FOR_DEFAULTS="${2:?}"
      shift 2
      ;;
    --keep-temps)
      KEEP_TEMPS=1
      shift
      ;;
    --autopkg-force)
      AUTOPKG_FORCE=1
      shift
      ;;
    --reset)
      RESET=1
      shift
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

BACKEND_URL="${BACKEND_URL%/}"

setup_autopkg_defaults() {
  local root="$1"
  echo "Creating directories under $root ..."
  mkdir -p \
    "$root/pkgs" \
    "$root/pkgsinfo" \
    "$root/AutoPkg/Overrides" \
    "$root/AutoPkg/repos" \
    "$root/AutoPkg/Reports" \
    "$root/AutoPkg/Cache" \
    "$HOME/Library/AutoPkg"

  echo "Writing AutoPkg preferences (com.github.autopkg) ..."
  defaults write com.github.autopkg CACHE_DIR "$root/AutoPkg/Cache"
  defaults write com.github.autopkg RECIPE_OVERRIDE_DIRS "$root/AutoPkg/Overrides/"
  defaults write com.github.autopkg RECIPE_REPO_DIR "$root/AutoPkg/repos/"
  defaults write com.github.autopkg FAIL_RECIPES_WITHOUT_TRUST_INFO -bool TRUE
  defaults write com.github.autopkg MUNKI_REPO "$root"
  if [[ -n "$GITHUB_TOKEN_FOR_DEFAULTS" ]]; then
    defaults write com.github.autopkg GITHUB_TOKEN "$GITHUB_TOKEN_FOR_DEFAULTS"
    echo "Set GITHUB_TOKEN in AutoPkg preferences."
  fi
  echo "Defaults applied. Repo root (MUNKI_REPO): $root"
}

resolve_autopkg_pref() {
  # Read a single ``defaults read com.github.autopkg <KEY>``. Echoes the
  # value (trailing newline trimmed) or empty string if unset/error.
  local key="$1"
  local val
  val="$(defaults read com.github.autopkg "$key" 2>/dev/null || true)"
  printf '%s' "${val}"
}

# Always align AutoPkg defaults with this run's workspace before invoking
# ``autopkg`` / ``cloud-autopkg-runner``. This is exactly what GHA does in
# the "Configure AutoPkg" step of autopkg_cloud_runner.yml. Without this,
# stale ``defaults`` from a previous project (different ``MUNKI_REPO`` or
# ``RECIPE_OVERRIDE_DIRS``) silently cause ``no_change`` because AutoPkg
# loads overrides / writes pkginfo to a tree we never touched.
# We only set keys that map to the run's workspace; ``RECIPE_REPOS``,
# ``GITHUB_TOKEN``, and other prefs are left alone.
ensure_run_defaults() {
  emulate -L zsh
  local root="$1"
  if [[ -z "$root" ]]; then
    echo "Error: ensure_run_defaults called without workspace" >&2
    return 1
  fi
  echo "==> Aligning AutoPkg defaults to workspace ${root} ..."
  local key want prev
  for spec in \
    "CACHE_DIR=${root}/AutoPkg/Cache" \
    "MUNKI_REPO=${root}" \
    "RECIPE_OVERRIDE_DIRS=${root}/AutoPkg/Overrides/" \
    "RECIPE_REPO_DIR=${root}/AutoPkg/repos/"; do
    key="${spec%%=*}"
    want="${spec#*=}"
    prev="$(resolve_autopkg_pref "$key")"
    if [[ "$prev" != "$want" ]]; then
      if [[ -n "$prev" ]]; then
        echo "    ${key}: '${prev}' -> '${want}'"
      else
        echo "    ${key}: (unset) -> '${want}'"
      fi
      defaults write com.github.autopkg "$key" "$want"
    fi
  done
  defaults write com.github.autopkg FAIL_RECIPES_WITHOUT_TRUST_INFO -bool TRUE
}

print_resolved_autopkg_paths() {
  echo "==> AutoPkg paths in effect (defaults read com.github.autopkg):"
  printf '    CACHE_DIR             = %s\n' "$(resolve_autopkg_pref CACHE_DIR)"
  printf '    MUNKI_REPO            = %s\n' "$(resolve_autopkg_pref MUNKI_REPO)"
  printf '    RECIPE_OVERRIDE_DIRS  = %s\n' "$(resolve_autopkg_pref RECIPE_OVERRIDE_DIRS)"
  printf '    RECIPE_REPO_DIR       = %s\n' "$(resolve_autopkg_pref RECIPE_REPO_DIR)"
}

# --reset: clear local AutoPkg state so the next run cannot short-circuit on
# previously imported pkginfo/downloads. Wipes AutoPkg's *actual* CACHE_DIR
# and MUNKI_REPO/{pkgsinfo,pkgs} (resolved via ``defaults read``), so the
# reset is correct even if those paths are not under the workspace.
# Recipe repos and overrides are kept (overrides are rewritten from the API
# every run, repos are global on this Mac).
# The cloud-autopkg-runner metadata cache is bypassed for this run (caller
# writes "{}" to metadata_cache.json after this returns).
reset_autopkg_state() {
  emulate -L zsh
  setopt null_glob
  local root="$1"
  if [[ -z "$root" || ! -d "$root" ]]; then
    echo "Error: --reset requires a valid workspace; got '${root}'" >&2
    return 1
  fi
  echo "==> --reset: clearing local AutoPkg state ..."

  local cache_dir munki_repo
  cache_dir="$(resolve_autopkg_pref CACHE_DIR)"
  munki_repo="$(resolve_autopkg_pref MUNKI_REPO)"
  [[ -z "$cache_dir" ]] && cache_dir="${root}/AutoPkg/Cache"
  [[ -z "$munki_repo" || "$munki_repo" == "./" || "$munki_repo" == "." ]] && munki_repo="$root"

  if [[ -d "$cache_dir" ]]; then
    echo "    Removing CACHE_DIR=${cache_dir}"
    rm -rf "$cache_dir"
  fi
  mkdir -p "$cache_dir"

  for sub in pkgsinfo pkgs; do
    local p="${munki_repo}/${sub}"
    # Defensive: never touch the filesystem root.
    if [[ -d "$p" && "$munki_repo" != "/" ]]; then
      echo "    Removing ${p}"
      rm -rf "$p"
    fi
    mkdir -p "$p"
  done
}

# Remove per-run scratch files from the repo root (default). Overrides under
# AutoPkg/Overrides/ are left in place — they are refreshed from the API next run.
cleanup_local_run_temps() {
  emulate -L zsh
  setopt null_glob
  local root="${GITHUB_WORKSPACE:-}"
  [[ -n "$root" && -d "$root" ]] || return 0
  echo "==> Cleaning up temporary run files ..."
  rm -f \
    "$root/metadata_cache_response.json" \
    "$root/metadata_cache.json" \
    "$root/run_config.json" \
    "$root/autopkg_runner.log" \
    "$root/AutoPkg/run_recipe_list.json" \
    "$root/AutoPkg/run_repo_list.txt"
  rm -f "$root/AutoPkg/Reports/"*.plist
}

if [[ "$SETUP_DEFAULTS_ONLY" -eq 1 ]]; then
  setup_autopkg_defaults "$WORKSPACE"
  exit 0
fi

if [[ -z "$BACKEND_URL" || -z "$RUN_ID" ]]; then
  echo "Error: --backend-url and --run-id are required (unless using --setup-defaults)." >&2
  usage >&2
  exit 1
fi

# Token order: 1) --token  2) repo .env (LOCAL_RUNNER_TOKEN)  3) AUTOMUNKI_API_TOKEN
# (file before env var so a stale export in the shell does not override the repo)
if [[ -z "${TOKEN:-}" && -f "$WORKSPACE/.env" ]]; then
  _from_env="$(python3 "${SCRIPT_DIR}/read_env_value.py" "$WORKSPACE/.env" LOCAL_RUNNER_TOKEN)"
  if [[ -n "$_from_env" ]]; then
    TOKEN="$_from_env"
    echo "==> Using LOCAL_RUNNER_TOKEN from ${WORKSPACE}/.env" >&2
  fi
fi
if [[ -n "${AUTOMUNKI_API_TOKEN:-}" && -z "$TOKEN" ]]; then
  TOKEN="$AUTOMUNKI_API_TOKEN"
  echo "==> Using AUTOMUNKI_API_TOKEN from environment" >&2
fi
if [[ -n "$TOKEN" ]]; then
  # Strip surrounding whitespace/CRs so compare_digest on the server matches
  TOKEN="$(python3 -c 'import sys; t=sys.argv[1]; print(t.strip().replace("\r",""), end="")' "$TOKEN")"
  export AUTOMUNKI_API_TOKEN="$TOKEN"
fi

export GITHUB_WORKSPACE="$WORKSPACE"
# Icon upload in report_results.py resolves ``icons/`` under this path (``defaults`` may differ).
export MUNKI_REPO="${MUNKI_REPO:-$GITHUB_WORKSPACE}"
export BACKEND_URL
export RUN_ID
cd "$GITHUB_WORKSPACE" || exit 1

if [[ "$KEEP_TEMPS" -eq 0 ]]; then
  trap cleanup_local_run_temps EXIT
fi

ensure_run_defaults "$GITHUB_WORKSPACE"
print_resolved_autopkg_paths

if [[ "$RESET" -eq 1 ]]; then
  reset_autopkg_state "$GITHUB_WORKSPACE"
fi

API_BASE="${BACKEND_URL}/api/v1/autopkg"

curl_auth() {
  if [[ -n "${TOKEN:-}" ]]; then
    curl -sS -H "Authorization: Bearer ${TOKEN}" "$@"
  else
    curl -sS "$@"
  fi
}

# When the UI created a run for specific recipe(s), the run row stores that list as
# recipe_filter. If we do not pass ?recipes= to GET /runs/config, the API returns
# every enabled override (same as GitHub Actions "full" run) — the Mac then runs
# the whole set. This block defaults RECIPE_FILTER from the run so single-recipe
# local runs only pull that override list unless you override with --recipes.
if [[ -z "$RECIPE_FILTER" ]]; then
  echo "==> Resolving recipe filter from run ${RUN_ID} ..." >&2
  if ! _run_json="$(curl_auth -sf "${API_BASE}/runs/${RUN_ID}" 2>/dev/null)"; then
    echo "Error: could not GET /autopkg/runs/${RUN_ID} (read run to apply recipe filter)." >&2
    echo "  If you use LOCAL_RUNNER_TOKEN, the server must allow that token to read the run" >&2
    echo "  (redeploy API). You can still pass an explicit list: --recipes 'RecipeA,RecipeB'" >&2
    echo "  or set RECIPE_FILTER before calling this script (comma-separated, same as the UI)." >&2
    exit 1
  fi
  RECIPE_FILTER="$(
    printf '%s' "$_run_json" | python3 -c '
import json, sys
d = json.load(sys.stdin)
r = d.get("recipe_filter")
if isinstance(r, list) and r:
    print(",".join(str(x).strip() for x in r if str(x).strip()), end="")
'
  )"
  if [[ -n "$RECIPE_FILTER" ]]; then
    echo "    Using run recipe filter: ${RECIPE_FILTER}" >&2
  else
    echo "    (run has no recipe filter — will use all enabled overrides in /runs/config)" >&2
  fi
fi

api_auth_hint() {
  echo "  For a long hex token: the *running* API must have LOCAL_RUNNER_TOKEN in its" >&2
  echo "  environment (match your .env) — if it is empty in the process, you always get 401." >&2
  echo "  Check: curl -sS ${BACKEND_URL}/health  —  \"local_runner_configured\" should be true." >&2
  echo "  Local dev: use --backend-url http://localhost:8000 (FastAPI), not :3000 (Vite UI)." >&2
  echo "  Or use a Munki Manager user JWT; see docs/local-autopkg-runner.md" >&2
}

if [[ "$RESET" -eq 1 ]]; then
  echo "==> --reset: skipping server metadata cache fetch (using empty cache)"
  echo '{}' > metadata_cache.json
else
  echo "==> Fetching metadata cache ..."
  HTTP_CODE=$(curl_auth -o metadata_cache_response.json -w "%{http_code}" "${API_BASE}/metadata-cache")
  if [[ "$HTTP_CODE" == "200" ]]; then
    python3 AutoPkg/scripts/load_metadata_cache.py
  elif [[ "$HTTP_CODE" == "401" || "$HTTP_CODE" == "403" ]]; then
    echo "Error: metadata-cache returned HTTP $HTTP_CODE (not authenticated)." >&2
    api_auth_hint
    exit 1
  else
    echo '{}' > metadata_cache.json
    echo "    (no cache or HTTP $HTTP_CODE; using empty cache)"
  fi
fi

QUERY=""
if [[ -n "$RECIPE_FILTER" ]]; then
  QUERY="?recipes=$(python3 -c 'import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))' "$RECIPE_FILTER")"
fi

echo "==> Fetching run config and writing overrides ..."
HTTP_CODE=$(curl_auth -o run_config.json -w "%{http_code}" "${API_BASE}/runs/config${QUERY}")
if [[ "$HTTP_CODE" != "200" ]]; then
  rm -f run_config.json
  echo "Error: run config failed (HTTP $HTTP_CODE)." >&2
  if [[ "$HTTP_CODE" == "401" || "$HTTP_CODE" == "403" ]]; then
    api_auth_hint
  fi
  exit 1
fi
python3 AutoPkg/scripts/write_overrides.py

echo "==> Adding recipe repos for this run ..."
xargs -L1 autopkg repo-add < AutoPkg/run_repo_list.txt

# Only update the repos this run actually needs. ``autopkg repo-update all``
# walks every repo ever added on this Mac, which is fine on an ephemeral
# GitHub-hosted runner but very slow on a long-lived Mac mini.
echo "==> Updating recipe repos for this run ..."
xargs -L1 autopkg repo-update < AutoPkg/run_repo_list.txt

# Defense-in-depth: walk each override's on-disk ParentRecipe chain and
# ``autopkg repo-add`` any repo the server-side ``run_repo_list.txt``
# missed (incomplete trust_info, chain deepened since last verify, etc.).
# Idempotent and a no-op when everything already resolves.
echo "==> Verifying parent recipe chain coverage ..."
if command -v uv >/dev/null 2>&1; then
  uv run --no-project --with pyyaml python3 "${SCRIPT_DIR}/ensure_parent_repos.py" \
    || python3 "${SCRIPT_DIR}/ensure_parent_repos.py"
else
  python3 "${SCRIPT_DIR}/ensure_parent_repos.py"
fi

# cloud-autopkg-runner loads ~/Library/Preferences/com.github.autopkg.plist in a new
# process. Flush the prefs domain so RECIPE_SEARCH_DIRS from repo-add is visible
# immediately (matches autopkg_cloud_runner.yml "Sync AutoPkg preferences to disk").
echo "==> Syncing AutoPkg preferences to disk ..."
defaults read com.github.autopkg >/dev/null 2>&1 || true

if [[ "$AUTOPKG_FORCE" -eq 1 ]]; then
  echo "==> Running AutoPkg sequentially (bypasses cloud-autopkg-runner) ..."
  AUTOPKG_BIN="$(command -v autopkg 2>/dev/null || true)"
  if [[ -z "$AUTOPKG_BIN" && -x /usr/local/bin/autopkg ]]; then
    AUTOPKG_BIN=/usr/local/bin/autopkg
  fi
  if [[ -z "$AUTOPKG_BIN" && -x /opt/homebrew/bin/autopkg ]]; then
    AUTOPKG_BIN=/opt/homebrew/bin/autopkg
  fi
  if [[ -z "$AUTOPKG_BIN" ]]; then
    echo "Error: autopkg not found. Install AutoPkg and ensure it is on PATH (or at /usr/local/bin or /opt/homebrew/bin)." >&2
    exit 1
  fi
  export AUTOPKG_BIN
  mkdir -p "$GITHUB_WORKSPACE/AutoPkg/Reports"
  python3 <<'PY'
import json
import os
import subprocess
import sys

ws = os.environ["GITHUB_WORKSPACE"]
ap = os.environ["AUTOPKG_BIN"]


def run_subcommand_supports_force() -> bool:
    r = subprocess.run(
        [ap, "run", "-h"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    out = (r.stdout or "") + (r.stderr or "")
    return "--force" in out


use_force = run_subcommand_supports_force()
if not use_force:
    print(
        "    Note: this autopkg build has no `run --force`; running without it "
        "(upgrade to a current AutoPkg 2.3+ pkg if you need forced re-downloads).",
        file=sys.stderr,
    )

path = os.path.join(ws, "AutoPkg", "run_recipe_list.json")
with open(path) as f:
    recipes = json.load(f)
for recipe in recipes:
    # Basename must match DB identifier stem (local.munki.<NAME>) for report_results.py
    if recipe.endswith(".munki.recipe"):
        product = recipe[: -len(".munki.recipe")]
        report_name = f"local.munki.{product}.plist"
    else:
        report_name = recipe.replace("/", "_") + ".plist"
    report = os.path.join(ws, "AutoPkg", "Reports", report_name)
    cmd = [ap, "run", recipe, "-v"]
    if use_force:
        cmd.append("--force")
    cmd.append(f"--report-plist={report}")
    print("   ", " ".join(cmd), flush=True)
    r = subprocess.run(cmd, cwd=ws)
    if r.returncode != 0:
        sys.exit(r.returncode)
sys.exit(0)
PY
else
  echo "==> Running cloud-autopkg-runner ..."
  uvx 'cloud-autopkg-runner' -v \
    --recipe-list AutoPkg/run_recipe_list.json \
    --cache-file metadata_cache.json \
    --cache-plugin json \
    --log-file autopkg_runner.log \
    --report-dir AutoPkg/Reports/
fi

echo "==> Saving metadata cache and reporting results ..."
export API_BASE_URL="$BACKEND_URL"
python3 AutoPkg/scripts/save_metadata_cache.py

REPORT_DIR="AutoPkg/Reports"
PKGSINFO_DIR="${GITHUB_WORKSPACE}/pkgsinfo"
mkdir -p "$PKGSINFO_DIR"

report_plists=("$REPORT_DIR"/*.plist(N))
if [[ ! -d "$REPORT_DIR" ]] || [[ ${#report_plists[@]} -eq 0 ]]; then
  echo "No report plists; marking run complete."
  curl_auth -sf -X POST "${API_BASE_URL}/api/v1/autopkg/runs/${RUN_ID}/complete" \
    -H "Content-Type: application/json" \
    -d '{}'
  echo "Done."
  exit 0
fi

export RUN_ID
for report in "$REPORT_DIR"/*.plist(N); do
  echo "    Processing ${report:t}"
  REPORT_FILE="$report" PKGSINFO_DIR="$PKGSINFO_DIR" python3 AutoPkg/scripts/report_results.py
done

curl_auth -sf -X POST "${API_BASE_URL}/api/v1/autopkg/runs/${RUN_ID}/complete" \
  -H "Content-Type: application/json" \
  -d '{}'

echo "Done."
