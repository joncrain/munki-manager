"""Walk on-disk recipe ``ParentRecipe`` chains and non-core processor deps,
``autopkg repo-add`` any repo that contains a missing parent or processor, and
report what was added.

Why this exists
===============

``infer_repos_from_trust_info`` (server-side) builds ``run_repo_list.txt``
from the recipe's stored ``trust_info`` (parent recipes + non-core processors).
When trust info is *incomplete* (because identifier resolution silently failed
during the original ``compute_trust_info``, or because the upstream parent
chain deepened after the user last verified), the runner clones only a partial
set of repos. AutoPkg then walks the on-disk chain at run time and emits:

    ERROR  Foo.munki   An error occurred while running 'check phase' on
    Foo.munki.recipe: Could not find parent recipe for com.github.X.Y

or, for third-party processors:

    WARNING: processor path not found for processor:
    com.github.grahampugh.recipes.commonprocessors/ChangeModeOwner
    Failed local trust verification.

This script defends against that by iterating every ``*.recipe`` /
``*.recipe.yaml`` under ``RECIPE_OVERRIDE_DIRS`` + ``RECIPE_REPO_DIR``,
following each ``ParentRecipe``, collecting non-core ``Processor`` steps from
every recipe in those chains, and ``autopkg repo-add``-ing the inferred repo
for any identifier or processor namespace it cannot resolve on disk. After
every new repo is cloned we re-scan and continue, so chains that go through
multiple authors (UTM: flammable -> ahousseini-recipes) get fully
materialised.

Safety:
  * No-op when every parent already resolves on disk.
  * Stops walking a branch when the identifier is not resolvable from
    its convention (so we never repo-add nonsense). AutoPkg's own error
    is then surfaced verbatim by the runner.
  * Idempotent: ``autopkg repo-add`` is a no-op when the repo is already
    cloned (it just prints "already exists").
  * Identifier-to-repo logic is a deliberate, minimal copy of
    ``backend/automunki/services/trust._repo_from_identifier``. Keeping
    it small and comment-aligned with the backend means drift is bounded
    to the few-line conversion below.
"""

from __future__ import annotations

import os
import plistlib
import re
import subprocess
import sys
from pathlib import Path

try:
    # PyYAML ships with AutoPkg's bundled Python on macOS runners, so it is
    # almost always importable when this script is invoked from the same
    # environment as ``autopkg``. The fallback below covers the rare case
    # of running under a stripped Python where ``.recipe.yaml`` files would
    # be silently skipped — better than crashing the whole step.
    import yaml as _yaml
except ImportError:  # pragma: no cover - environment fallback
    _yaml = None


# ── Identifier → repo (mirrors backend ``_repo_from_identifier``) ───────────


# AutoPkg core processors — no separate repo needed (mirrors backend trust.py).
_CORE_PROCESSORS = frozenset(
    {
        "Copier",
        "CURLDownloader",
        "CURLTextSearcher",
        "CodeSignatureVerifier",
        "DmgCreator",
        "DmgMounter",
        "Downloader",
        "EndOfCheckPhase",
        "FileFinder",
        "FileMover",
        "FlatPkgPacker",
        "FlatPkgUnpacker",
        "GitHubReleasesInfoProvider",
        "Installer",
        "InstallFromDMG",
        "MunkiCatalogBuilder",
        "MunkiImporter",
        "MunkiInstallsItemsCreator",
        "MunkiPkginfoMerger",
        "MunkiSetDefaultCatalog",
        "PackageRequired",
        "PathDeleter",
        "PkgCopier",
        "PkgCreator",
        "PkgExtractor",
        "PkgInfoCreator",
        "PkgPayloadUnpacker",
        "PlistEditor",
        "PlistReader",
        "SparkleUpdateInfoProvider",
        "StopProcessingIf",
        "Symlinker",
        "Unarchiver",
        "URLDownloader",
        "URLGetter",
        "URLTextSearcher",
        "Versioner",
    }
)


def _repo_from_identifier(identifier: str) -> str | None:
    """Mirror of ``backend/automunki/services/trust._repo_from_identifier``.

    Convention:
      * ``com.github.autopkg.<user>.<type>.<name>`` -> ``autopkg/<user>-recipes``
      * ``com.github.<user>.<type>.<name>``        -> ``autopkg/<user>-recipes``
      * ``com.<author>.<type>.<name>``             -> ``autopkg/<author>-recipes``
      * If the user/author segment already ends with ``-recipes``, that segment
        IS the repo name (UTM grandparent case).
    """
    parts = identifier.split(".")

    def _suffix(seg: str) -> str:
        return seg if seg.endswith("-recipes") else f"{seg}-recipes"

    if len(parts) >= 5 and parts[:3] == ["com", "github", "autopkg"]:
        return f"autopkg/{_suffix(parts[3])}"
    if len(parts) >= 5 and parts[:2] == ["com", "github"]:
        return f"autopkg/{_suffix(parts[2])}"
    if len(parts) >= 4 and parts[0] == "com" and parts[1] != "github":
        return f"autopkg/{_suffix(parts[1])}"
    return None


def _processor_namespace(processor_name: str) -> str | None:
    """Return the recipe-repo namespace for a namespaced processor."""
    if "/" not in processor_name:
        return None
    return processor_name.split("/", 1)[0]


def _repo_for_processor(processor_name: str) -> str | None:
    """Infer the GitHub repo that hosts a namespaced processor."""
    namespace = _processor_namespace(processor_name)
    if not namespace:
        return None
    return _repo_from_identifier(namespace)


def _extract_non_core_processors(recipe_data: dict) -> list[str]:
    """Collect non-core processor names from a recipe's Process list."""
    processors: set[str] = set()
    for step in recipe_data.get("Process", []):
        proc_name = step.get("Processor", "")
        base_name = proc_name.rsplit("/", 1)[-1] if "/" in proc_name else proc_name
        if base_name and base_name not in _CORE_PROCESSORS:
            processors.add(proc_name)
    return sorted(processors)


def _processor_on_disk(repo_dir: Path, processor_name: str) -> bool:
    """Return True when ``{ClassName}.py`` exists anywhere under ``repo_dir``."""
    proc_class = processor_name.rsplit("/", 1)[-1]
    if not proc_class:
        return False
    for pattern in (f"{proc_class}.py", f"{proc_class}.recipe"):
        if next(repo_dir.rglob(pattern), None) is not None:
            return True
    return False


# ── Recipe parsing ──────────────────────────────────────────────────────────

_RECIPE_GLOBS = ("*.recipe", "*.recipe.yaml")


def _parse_recipe(path: Path) -> dict | None:
    """Parse a recipe file (plist or yaml). Returns ``None`` on error.

    YAML is only attempted when PyYAML is importable; otherwise YAML
    recipes are silently skipped. The chain walker is best-effort by
    design — anything we can't parse here will just be re-attempted by
    AutoPkg, which surfaces its own error.
    """
    try:
        if path.suffix == ".yaml" or path.name.endswith(".recipe.yaml"):
            if _yaml is None:
                return None
            with open(path) as f:
                data = _yaml.safe_load(f)
        else:
            with open(path, "rb") as f:
                data = plistlib.load(f)
        if isinstance(data, dict):
            return data
        return None
    except Exception:
        return None


def _scan_recipes(root: Path) -> dict[str, Path]:
    """Build an ``identifier -> file path`` map for every recipe under ``root``.

    ``root`` is typically ``RECIPE_REPO_DIR`` (clones of upstream recipe
    repos). Local override dirs are scanned separately as starting points
    so the map only contains "library" recipes whose Identifier is
    canonical.
    """
    out: dict[str, Path] = {}
    if not root.is_dir():
        return out
    for pattern in _RECIPE_GLOBS:
        for p in root.rglob(pattern):
            data = _parse_recipe(p)
            if not data:
                continue
            ident = data.get("Identifier")
            if isinstance(ident, str) and ident not in out:
                out[ident] = p
    return out


def _starting_parents(override_dirs: list[Path]) -> list[str]:
    """Collect ``ParentRecipe`` identifiers from every override file."""
    parents: list[str] = []
    for d in override_dirs:
        if not d.is_dir():
            continue
        for pattern in _RECIPE_GLOBS:
            for p in d.rglob(pattern):
                data = _parse_recipe(p)
                if not data:
                    continue
                parent = data.get("ParentRecipe")
                if isinstance(parent, str) and parent.strip():
                    parents.append(parent.strip())
    return parents


# ── ``autopkg repo-add`` driver ─────────────────────────────────────────────


def _run_repo_add(repo: str) -> bool:
    """Run ``autopkg repo-add <repo>``. Returns True if the command succeeded.

    AutoPkg accepts both ``owner/repo`` and full URLs; we use the short
    form because that is what ``_repo_from_identifier`` produces.
    """
    print(f"   repo-add {repo}", flush=True)
    try:
        r = subprocess.run(
            ["autopkg", "repo-add", repo],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        print(f"   repo-add failed: {exc}", file=sys.stderr, flush=True)
        return False
    if r.returncode != 0:
        msg = (r.stderr or r.stdout or "").strip()
        print(f"   repo-add exit={r.returncode}: {msg}", file=sys.stderr, flush=True)
        return False
    return True


# ── Resolve AutoPkg paths from the environment ──────────────────────────────


def _autopkg_pref(key: str) -> str:
    """Read a single ``defaults read com.github.autopkg <key>``.

    Mirrors what the runner does in ``run_local_autopkg.sh``: relies on
    AutoPkg's own preference domain rather than hard-coding paths. Returns
    an empty string when the key is unset or ``defaults`` isn't on PATH.
    """
    try:
        r = subprocess.run(
            ["defaults", "read", "com.github.autopkg", key],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""
    if r.returncode != 0:
        return ""
    return r.stdout.strip()


def _resolve_paths() -> tuple[Path, list[Path]]:
    """Return ``(recipe_repo_dir, override_dirs)`` from AutoPkg prefs / env.

    ``RECIPE_OVERRIDE_DIRS`` may be a colon-separated list per upstream
    convention; we accept either form.
    """
    repo_dir = os.environ.get("AUTOPKG_RECIPE_REPO_DIR") or _autopkg_pref("RECIPE_REPO_DIR")
    if not repo_dir:
        ws = os.environ.get("GITHUB_WORKSPACE", "")
        if ws:
            repo_dir = str(Path(ws) / "AutoPkg" / "repos")
    if not repo_dir:
        print(
            "   ensure_parent_repos: RECIPE_REPO_DIR is not set and GITHUB_WORKSPACE is empty; nothing to do.",
            file=sys.stderr,
            flush=True,
        )
        return Path("/nonexistent"), []

    overrides_raw = os.environ.get("AUTOPKG_RECIPE_OVERRIDE_DIRS") or _autopkg_pref("RECIPE_OVERRIDE_DIRS")
    if not overrides_raw:
        ws = os.environ.get("GITHUB_WORKSPACE", "")
        if ws:
            overrides_raw = str(Path(ws) / "AutoPkg" / "Overrides")
    overrides = [Path(p) for p in re.split(r"[:\n]+", overrides_raw or "") if p.strip()]
    return Path(repo_dir), overrides


# ── Main walk ───────────────────────────────────────────────────────────────


def ensure_parent_repos(max_repo_adds: int = 32) -> int:
    """Walk every override's parent chain and processor deps; ``repo-add`` gaps.

    Returns the number of repos added (so the caller can print a summary
    or skip a follow-up ``defaults read`` flush when nothing changed).
    """
    repo_dir, override_dirs = _resolve_paths()
    if not override_dirs:
        print("   ensure_parent_repos: no override dirs found; skipping.", flush=True)
        return 0

    starting = _starting_parents(override_dirs)
    if not starting:
        print("   ensure_parent_repos: no overrides with ParentRecipe; skipping.", flush=True)
        return 0

    repo_map = _scan_recipes(repo_dir)
    visited: set[str] = set()
    queue: list[str] = list(dict.fromkeys(starting))
    added: list[str] = []
    attempted_repos: set[str] = set()
    pending_processors: set[str] = set()

    def _maybe_repo_add(inferred: str | None) -> bool:
        """``repo-add`` when ``inferred`` is new; re-scan ``repo_map`` on success."""
        nonlocal repo_map
        if not inferred or inferred in attempted_repos:
            return False
        if len(added) >= max_repo_adds:
            print(
                f"   ensure_parent_repos: hit max {max_repo_adds} repo-adds; refusing to add more.",
                file=sys.stderr,
                flush=True,
            )
            return False
        attempted_repos.add(inferred)
        if _run_repo_add(inferred):
            added.append(inferred)
            repo_map = _scan_recipes(repo_dir)
            return True
        return False

    while queue or pending_processors:
        if queue:
            ident = queue.pop(0)
            if ident in visited:
                continue
            visited.add(ident)

            recipe_path = repo_map.get(ident)
            if recipe_path is None:
                inferred = _repo_from_identifier(ident)
                if not inferred:
                    continue
                if _maybe_repo_add(inferred):
                    recipe_path = repo_map.get(ident)
                if recipe_path is None:
                    continue

            data = _parse_recipe(recipe_path)
            if not data:
                continue

            for proc_name in _extract_non_core_processors(data):
                if _processor_on_disk(repo_dir, proc_name):
                    continue
                namespace = _processor_namespace(proc_name)
                if namespace:
                    pending_processors.add(proc_name)

            next_parent = data.get("ParentRecipe")
            if isinstance(next_parent, str) and next_parent.strip():
                queue.append(next_parent.strip())
            continue

        # Processor pass: repo-add the inferred home for each missing processor.
        proc_name = pending_processors.pop()
        if _processor_on_disk(repo_dir, proc_name):
            continue
        inferred = _repo_for_processor(proc_name)
        if not inferred:
            continue
        _maybe_repo_add(inferred)

    if added:
        print(
            f"   ensure_parent_repos: added {len(added)} repo(s) the trust info missed: " + ", ".join(added),
            flush=True,
        )
    else:
        print("   ensure_parent_repos: every parent chain already resolved on disk.", flush=True)
    return len(added)


if __name__ == "__main__":
    n = ensure_parent_repos()
    sys.exit(0 if n >= 0 else 1)
