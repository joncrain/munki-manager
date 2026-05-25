"""Download the metadata cache from the Munki Manager API into ``metadata_cache.json``.

``cloud-autopkg-runner`` writes per-recipe cache entries that include an
absolute ``file_path``. Those paths are rooted in the *previous* runner's
workspace, e.g. ``/Users/runner/work/<owner>/<repo>/AutoPkg/Cache/...`` from
GitHub Actions or ``/opt/UnitySrc/joncrain/munki-manager/AutoPkg/Cache/...``
from a Mac mini.

The server now stores those entries with a ``${WORKSPACE}`` placeholder
(see :mod:`automunki.services.autopkg_metadata_cache`), but legacy data
written before that change still has raw absolute paths. This script
handles both:

1. ``${WORKSPACE}/AutoPkg/Cache/...`` → expand to current ``GITHUB_WORKSPACE``.
2. ``<other-runner-workspace>/AutoPkg/Cache/...`` → rewrite to current
   ``GITHUB_WORKSPACE``. We use ``/AutoPkg/Cache/`` as the anchor because
   ``cloud-autopkg-runner``'s ``CACHE_DIR`` is configured to
   ``<workspace>/AutoPkg/Cache`` on every supported runner.

If ``GITHUB_WORKSPACE`` is unset (someone running this script outside the
runner environment) we leave paths alone — there's no safe target to rewrite to.
"""

from __future__ import annotations

import json
import os

WORKSPACE_PLACEHOLDER = "${WORKSPACE}"
CACHE_ANCHOR = "/AutoPkg/Cache/"


def _rewrite_file_path(path: str, workspace: str) -> str:
    """Rewrite a single ``file_path`` value to point at *this* runner's workspace.

    Three input forms are recognised; everything else passes through:

    - ``${WORKSPACE}/AutoPkg/Cache/...`` (new normalized form).
    - ``<previous-workspace>/AutoPkg/Cache/...`` (legacy data from any runner;
      the prefix before ``/AutoPkg/Cache/`` is the previous workspace and we
      replace it).
    - Anything without ``/AutoPkg/Cache/`` (manually placed file etc.) is left
      alone so we don't corrupt unfamiliar data — show it as-is in logs.
    """
    if not isinstance(path, str) or not path:
        return path
    if path.startswith(WORKSPACE_PLACEHOLDER):
        return workspace.rstrip("/") + path[len(WORKSPACE_PLACEHOLDER) :]
    idx = path.find(CACHE_ANCHOR)
    if idx > 0:
        return workspace.rstrip("/") + path[idx:]
    return path


def _rewrite_paths(obj: object, workspace: str) -> object:
    """Recursively rewrite every ``file_path`` value found in the cache.

    Walks dicts and lists; only the value of a ``file_path`` key is rewritten.
    This is narrower than the previous "rewrite any string that looks
    runner-rooted" heuristic because we only ever stored absolute paths in
    that one field; touching anything else risked corrupting recipe trust
    info or repo URLs.
    """
    if isinstance(obj, dict):
        return {
            k: (_rewrite_file_path(v, workspace) if k == "file_path" and isinstance(v, str) else _rewrite_paths(v, workspace))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_rewrite_paths(v, workspace) for v in obj]
    return obj


def main() -> None:
    response_file = "metadata_cache_response.json"
    output_file = "metadata_cache.json"

    if not os.path.exists(response_file):
        print("No API response file found, starting with empty cache")
        with open(output_file, "w") as f:
            json.dump({}, f)
        return

    with open(response_file) as f:
        resp = json.load(f)

    cache = resp.get("cache_data", {})
    ws = os.environ.get("GITHUB_WORKSPACE", "").strip()
    if ws:
        before = json.dumps(cache)
        cache = _rewrite_paths(cache, ws)
        if json.dumps(cache) != before:
            print(f"Rewrote cache file_path entries → workspace={ws!r}")

    with open(output_file, "w") as f:
        json.dump(cache, f, indent=4)
    print(f"Loaded metadata cache with {len(cache)} entries")


if __name__ == "__main__":
    main()
