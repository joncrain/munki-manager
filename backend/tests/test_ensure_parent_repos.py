"""Tests for ``AutoPkg/scripts/ensure_parent_repos.py``.

The script is the runner-side safety net for the "incomplete trust info
silently leaves parent repos out of ``run_repo_list.txt``" failure mode
(UTM grandparent ``com.github.ahousseini-recipes.download.UTM``,
WhatsApp scriptingosx chain, etc.). It walks each override's on-disk
``ParentRecipe`` chain and ``autopkg repo-add``s the inferred repo for
any unresolved ancestor.

These tests pin the most important behaviours without spawning real
``autopkg`` subprocesses or touching ``defaults``:

* identifier-to-repo conversion mirrors the backend conventions
  (including the UTM ``-recipes``-suffix special case);
* the walker collects every starting ``ParentRecipe`` from override
  files;
* unresolved chain entries trigger a single ``repo-add`` per inferred
  repo (idempotent, capped, deduplicated);
* a chain that already resolves entirely on disk produces zero
  ``repo-add`` calls;
* convention-unknown identifiers don't trigger random ``repo-add``s.
"""

from __future__ import annotations

import importlib.util
import plistlib
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# The script lives under ``AutoPkg/scripts``; load it as a module so we can
# call its helpers directly without needing a real ``autopkg`` on PATH.
_SCRIPT = Path(__file__).resolve().parents[2] / "AutoPkg" / "scripts" / "ensure_parent_repos.py"
_spec = importlib.util.spec_from_file_location("ensure_parent_repos", _SCRIPT)
assert _spec and _spec.loader
ensure_parent_repos = importlib.util.module_from_spec(_spec)
sys.modules["ensure_parent_repos"] = ensure_parent_repos
_spec.loader.exec_module(ensure_parent_repos)


# ── _repo_from_identifier (mirrors backend) ────────────────────────────────


@pytest.mark.parametrize(
    "identifier,expected",
    [
        # Long form com.github.autopkg.<user>.<type>.<name>.
        (
            "com.github.autopkg.wardsparadox.munki.Ghostty",
            "autopkg/wardsparadox-recipes",
        ),
        # com.github.<user>.<type>.<name>.
        (
            "com.github.swy.download.BraveUniversal",
            "autopkg/swy-recipes",
        ),
        # Short form com.<author>.<type>.<name>.
        (
            "com.scriptingosx.munki.WhatsApp",
            "autopkg/scriptingosx-recipes",
        ),
        # UTM grandparent: middle segment already ends in ``-recipes`` —
        # don't double-suffix.
        (
            "com.github.ahousseini-recipes.download.UTM",
            "autopkg/ahousseini-recipes",
        ),
    ],
)
def test_repo_from_identifier_mirrors_backend(identifier: str, expected: str) -> None:
    assert ensure_parent_repos._repo_from_identifier(identifier) == expected


def test_repo_from_identifier_unknown_returns_none() -> None:
    assert ensure_parent_repos._repo_from_identifier("totally.unrelated") is None
    assert ensure_parent_repos._repo_from_identifier("nodots") is None


# ── helpers for the on-disk fixtures ────────────────────────────────────────


def _write_recipe(path: Path, identifier: str, parent: str | None) -> None:
    """Write a minimal AutoPkg-shaped plist recipe."""
    data: dict = {"Identifier": identifier, "Input": {"NAME": identifier.split(".")[-1]}}
    if parent:
        data["ParentRecipe"] = parent
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        plistlib.dump(data, f)


# ── _scan_recipes / _starting_parents ──────────────────────────────────────


def test_scan_recipes_indexes_every_identifier(tmp_path: Path) -> None:
    """Recursively walking the repo dir produces an ``identifier -> path`` map."""
    repo_dir = tmp_path / "repos"
    _write_recipe(
        repo_dir / "flammable-recipes" / "UTM" / "UTM.munki.recipe",
        identifier="com.github.flammable.munki.UTM",
        parent="com.github.ahousseini-recipes.download.UTM",
    )
    _write_recipe(
        repo_dir / "ahousseini-recipes" / "UTM" / "UTM.download.recipe",
        identifier="com.github.ahousseini-recipes.download.UTM",
        parent=None,
    )
    repo_map = ensure_parent_repos._scan_recipes(repo_dir)
    assert "com.github.flammable.munki.UTM" in repo_map
    assert "com.github.ahousseini-recipes.download.UTM" in repo_map


def test_starting_parents_collects_each_overrides_parent(tmp_path: Path) -> None:
    overrides = tmp_path / "Overrides"
    _write_recipe(
        overrides / "UTM.munki.recipe",
        identifier="local.munki.UTM",
        parent="com.github.flammable.munki.UTM",
    )
    _write_recipe(
        overrides / "Firefox.munki.recipe",
        identifier="local.munki.Firefox",
        parent="com.github.autopkg.recipes.Mozilla.Firefox",
    )
    parents = ensure_parent_repos._starting_parents([overrides])
    assert "com.github.flammable.munki.UTM" in parents
    assert "com.github.autopkg.recipes.Mozilla.Firefox" in parents


# ── ensure_parent_repos: full-walk integration with mocked repo-add ─────────


def _patch_paths(monkeypatch: pytest.MonkeyPatch, repo_dir: Path, overrides: Path) -> None:
    """Pretend ``defaults`` returned the given paths."""

    def _resolve():
        return repo_dir, [overrides]

    monkeypatch.setattr(ensure_parent_repos, "_resolve_paths", _resolve)


def test_no_action_when_full_chain_already_on_disk(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Firefox/Cursor happy path: server-side ``run_repo_list.txt`` was
    complete, every parent is already cloned. The script must not call
    ``repo-add`` at all (it would slow every run by ~1s otherwise)."""
    repo_dir = tmp_path / "repos"
    overrides = tmp_path / "Overrides"
    _write_recipe(
        overrides / "UTM.munki.recipe",
        identifier="local.munki.UTM",
        parent="com.github.flammable.munki.UTM",
    )
    _write_recipe(
        repo_dir / "flammable-recipes" / "UTM" / "UTM.munki.recipe",
        identifier="com.github.flammable.munki.UTM",
        parent="com.github.ahousseini-recipes.download.UTM",
    )
    _write_recipe(
        repo_dir / "ahousseini-recipes" / "UTM" / "UTM.download.recipe",
        identifier="com.github.ahousseini-recipes.download.UTM",
        parent=None,
    )
    _patch_paths(monkeypatch, repo_dir, overrides)
    with patch.object(ensure_parent_repos, "_run_repo_add") as mock_add:
        added = ensure_parent_repos.ensure_parent_repos()
    assert added == 0
    mock_add.assert_not_called()


def test_adds_missing_grandparent_repo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The UTM bug we are fixing: only the immediate parent's repo is on
    disk; the grandparent lives in a different repo and is missing. The
    script should ``repo-add`` exactly one repo (the grandparent's) and
    re-scan so the chain resolves on the second pass."""
    repo_dir = tmp_path / "repos"
    overrides = tmp_path / "Overrides"
    _write_recipe(
        overrides / "UTM.munki.recipe",
        identifier="local.munki.UTM",
        parent="com.github.flammable.munki.UTM",
    )
    _write_recipe(
        repo_dir / "flammable-recipes" / "UTM" / "UTM.munki.recipe",
        identifier="com.github.flammable.munki.UTM",
        parent="com.github.ahousseini-recipes.download.UTM",
    )

    def _fake_repo_add(repo: str) -> bool:
        # Simulate ``autopkg repo-add`` cloning the grandparent.
        if repo == "autopkg/ahousseini-recipes":
            _write_recipe(
                repo_dir / "ahousseini-recipes" / "UTM" / "UTM.download.recipe",
                identifier="com.github.ahousseini-recipes.download.UTM",
                parent=None,
            )
            return True
        return False

    _patch_paths(monkeypatch, repo_dir, overrides)
    with patch.object(ensure_parent_repos, "_run_repo_add", side_effect=_fake_repo_add) as mock_add:
        added = ensure_parent_repos.ensure_parent_repos()

    assert added == 1
    mock_add.assert_called_once_with("autopkg/ahousseini-recipes")


def test_does_not_repo_add_when_identifier_convention_unrecognised(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A parent identifier that doesn't match any convention must NOT
    trigger a guess at ``repo-add``. AutoPkg's own "Could not find parent
    recipe" error is the right signal in that case (better than us
    cloning a random repo that probably doesn't exist)."""
    repo_dir = tmp_path / "repos"
    overrides = tmp_path / "Overrides"
    _write_recipe(
        overrides / "Weird.munki.recipe",
        identifier="local.munki.Weird",
        parent="totally.unrelated.parent",
    )
    repo_dir.mkdir()
    _patch_paths(monkeypatch, repo_dir, overrides)
    with patch.object(ensure_parent_repos, "_run_repo_add") as mock_add:
        added = ensure_parent_repos.ensure_parent_repos()
    assert added == 0
    mock_add.assert_not_called()


def test_does_not_retry_repo_when_identifier_still_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If we ``repo-add`` a repo that should contain the identifier but
    actually doesn't (convention misled us, or upstream rename), we must
    not retry the same repo for every other unresolved sibling."""
    repo_dir = tmp_path / "repos"
    overrides = tmp_path / "Overrides"
    _write_recipe(
        overrides / "A.munki.recipe",
        identifier="local.munki.A",
        parent="com.github.scriptingosx.munki.MissingA",
    )
    _write_recipe(
        overrides / "B.munki.recipe",
        identifier="local.munki.B",
        parent="com.github.scriptingosx.munki.MissingB",
    )
    repo_dir.mkdir()

    calls: list[str] = []

    def _fake_repo_add(repo: str) -> bool:
        calls.append(repo)
        return True  # "Cloned" but provides nothing — repo just doesn't host these.

    _patch_paths(monkeypatch, repo_dir, overrides)
    with patch.object(ensure_parent_repos, "_run_repo_add", side_effect=_fake_repo_add):
        ensure_parent_repos.ensure_parent_repos()

    # Only one repo-add even though two sibling overrides reference
    # identifiers that infer the same repo.
    assert calls == ["autopkg/scriptingosx-recipes"]


def test_caps_repo_adds_at_safety_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defensive cap: a malformed / cyclic chain must not be allowed to
    spam ``repo-add`` indefinitely."""
    repo_dir = tmp_path / "repos"
    overrides = tmp_path / "Overrides"
    # 5 distinct overrides, each pointing at a different inferred repo,
    # cap the run at 2 to confirm the limit fires.
    for i in range(5):
        _write_recipe(
            overrides / f"R{i}.munki.recipe",
            identifier=f"local.munki.R{i}",
            parent=f"com.author{i}.munki.Thing",
        )
    repo_dir.mkdir()
    _patch_paths(monkeypatch, repo_dir, overrides)
    with patch.object(ensure_parent_repos, "_run_repo_add", return_value=True) as mock_add:
        added = ensure_parent_repos.ensure_parent_repos(max_repo_adds=2)
    assert added == 2
    assert mock_add.call_count == 2


def _write_recipe_with_processors(
    path: Path,
    identifier: str,
    parent: str | None,
    processors: list[str],
) -> None:
    data: dict = {
        "Identifier": identifier,
        "Input": {"NAME": identifier.split(".")[-1]},
        "Process": [{"Processor": p} for p in processors],
    }
    if parent:
        data["ParentRecipe"] = parent
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        plistlib.dump(data, f)


def test_adds_missing_processor_repo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """1Password-style failure: parent recipe references a third-party processor
    whose repo was never in ``run_repo_list.txt``."""
    repo_dir = tmp_path / "repos"
    overrides = tmp_path / "Overrides"
    _write_recipe(
        overrides / "1Password.munki.recipe",
        identifier="local.munki.1Password",
        parent="com.github.dataJAR-recipes.munki.1Password",
    )
    _write_recipe_with_processors(
        repo_dir / "dataJAR-recipes" / "1Password" / "1Password.munki.recipe",
        identifier="com.github.dataJAR-recipes.munki.1Password",
        parent="com.github.dataJAR-recipes.download.1Password",
        processors=[
            "FlatPkgUnpacker",
            "com.github.grahampugh.recipes.commonprocessors/ChangeModeOwner",
        ],
    )
    _write_recipe(
        repo_dir / "dataJAR-recipes" / "1Password" / "1Password.download.recipe",
        identifier="com.github.dataJAR-recipes.download.1Password",
        parent=None,
    )

    def _fake_repo_add(repo: str) -> bool:
        if repo == "autopkg/grahampugh-recipes":
            proc_dir = repo_dir / "grahampugh-recipes" / "CommonProcessors"
            proc_dir.mkdir(parents=True, exist_ok=True)
            (proc_dir / "ChangeModeOwner.py").write_text("# stub")
            return True
        return False

    _patch_paths(monkeypatch, repo_dir, overrides)
    with patch.object(ensure_parent_repos, "_run_repo_add", side_effect=_fake_repo_add) as mock_add:
        added = ensure_parent_repos.ensure_parent_repos()

    assert added == 1
    mock_add.assert_called_once_with("autopkg/grahampugh-recipes")
    assert ensure_parent_repos._processor_on_disk(
        repo_dir,
        "com.github.grahampugh.recipes.commonprocessors/ChangeModeOwner",
    )
