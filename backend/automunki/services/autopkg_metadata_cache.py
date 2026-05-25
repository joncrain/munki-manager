"""Path normalization for the cloud-autopkg-runner metadata cache.

``cloud-autopkg-runner`` writes ``metadata_cache.json`` entries that contain
absolute filesystem paths (the ``file_path`` of each downloaded artifact),
e.g. ::

    /Users/runner/work/munki-manager/munki-manager/AutoPkg/Cache/local.munki.Firefox/downloads/Firefox.dmg
    /opt/UnitySrc/joncrain/munki-manager/AutoPkg/Cache/local.munki.BetterTouchTool/downloads/BetterTouchTool.zip

When the same Munki Manager API serves both **GitHub-hosted runners** (workspace
``/Users/runner/work/<owner>/<repo>``) and a **long-lived Mac mini / dev Mac**
(workspace e.g. ``/opt/UnitySrc/joncrain/munki-manager``), passing the cache
through unchanged means the next runner's worker tries to ``os.path.exists()``
the previous runner's path and bombs with ``FileNotFoundError`` (or worse,
``PermissionError`` if it stumbles into someone else's home directory).

The fix is to make storage **runner-agnostic**. On upload (``PUT
/metadata-cache``) we strip the leading workspace and replace it with a
placeholder ``${WORKSPACE}``; on download (``GET /metadata-cache``) we expand
the placeholder back to the requesting runner's workspace. The shape of the
JSON stays the same — only the leading directory of ``file_path`` changes.

Anchor: the path under ``${WORKSPACE}`` is always
``AutoPkg/Cache/<identifier>/downloads/<filename>``. We use the
``/AutoPkg/Cache/`` segment as the splitter because it's set by ``CACHE_DIR``
on every runner (see ``run_local_autopkg.sh::ensure_run_defaults`` and the
GitHub Actions workflow's ``Configure AutoPkg`` step), and any path we don't
recognise (e.g. someone manually placed a file outside the workspace) is
left alone.
"""

from __future__ import annotations

from typing import Any

#: Placeholder that replaces the runner-specific workspace prefix in stored cache
#: entries. Format chosen to be (a) impossible to confuse with a real path and
#: (b) easy to grep for if anything ever leaks through.
WORKSPACE_PLACEHOLDER = "${WORKSPACE}"

#: The path segment that anchors the rewrite. ``cloud-autopkg-runner``'s
#: ``CACHE_DIR`` is configured to ``<workspace>/AutoPkg/Cache`` on every
#: supported runner, so any ``file_path`` containing this segment can be
#: split safely into ``<workspace>`` + ``AutoPkg/Cache/...``.
_CACHE_ANCHOR = "/AutoPkg/Cache/"


def _normalize_file_path(path: str) -> str:
    """Replace ``<workspace>/AutoPkg/Cache/...`` with ``${WORKSPACE}/AutoPkg/Cache/...``.

    Idempotent: paths that already start with the placeholder pass through
    unchanged. Paths that don't contain the cache anchor (e.g. absolute paths
    to files outside ``CACHE_DIR``) are left alone — we'd rather show the
    weird path in logs than corrupt it.
    """
    if not isinstance(path, str) or not path:
        return path
    if path.startswith(WORKSPACE_PLACEHOLDER):
        return path
    idx = path.find(_CACHE_ANCHOR)
    if idx <= 0:
        return path
    return f"{WORKSPACE_PLACEHOLDER}{path[idx:]}"


def _expand_file_path(path: str, workspace: str) -> str:
    """Inverse of :func:`_normalize_file_path` for runners pulling the cache."""
    if not isinstance(path, str) or not path:
        return path
    if not workspace or not path.startswith(WORKSPACE_PLACEHOLDER):
        return path
    return workspace.rstrip("/") + path[len(WORKSPACE_PLACEHOLDER) :]


def normalize_cache_entry(entry: Any) -> Any:
    """Strip runner-specific workspace prefixes from a single cache entry.

    A cache entry is the JSON value the runner stores per recipe; the only
    field we touch is ``metadata[i].file_path``. The rest of the structure
    (``etag``, ``file_size``, ``last_modified``, ``timestamp``, …) is
    runner-portable and round-trips unchanged.

    Returning a *new* dict (rather than mutating in place) keeps the API
    handlers free of "did this entry come from the request body or the DB"
    aliasing concerns.
    """
    if not isinstance(entry, dict):
        return entry
    new_entry = dict(entry)
    metadata = new_entry.get("metadata")
    if isinstance(metadata, list):
        new_entry["metadata"] = [
            (
                {**item, "file_path": _normalize_file_path(item["file_path"])}
                if (isinstance(item, dict) and "file_path" in item)
                else item
            )
            for item in metadata
        ]
    return new_entry


def expand_cache_entry(entry: Any, workspace: str) -> Any:
    """Replace ``${WORKSPACE}`` with the requesting runner's workspace.

    Called when serving ``GET /metadata-cache`` so the runner that loads
    ``metadata_cache.json`` sees real absolute paths it can ``stat()``.
    Old, never-normalized entries (legacy data written before this code
    landed) are returned untouched — :mod:`AutoPkg/scripts/load_metadata_cache.py`
    has a defensive fallback for those.
    """
    if not isinstance(entry, dict) or not workspace:
        return entry
    new_entry = dict(entry)
    metadata = new_entry.get("metadata")
    if isinstance(metadata, list):
        new_entry["metadata"] = [
            (
                {**item, "file_path": _expand_file_path(item["file_path"], workspace)}
                if (isinstance(item, dict) and "file_path" in item)
                else item
            )
            for item in metadata
        ]
    return new_entry
