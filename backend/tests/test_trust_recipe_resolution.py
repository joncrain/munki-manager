"""Tests for recipe identifier → GitHub path resolution in ``services.trust``.

Zoom is the canonical failure: ``com.github.hansen-m.download.zoomus`` lives at
``Zoom/Zoom.download.recipe``. Filename-based resolution used to stop at the two
homebysix ancestors, so verify reported ``verified`` while AutoPkg's on-disk
chain (after ``ensure_parent_repos`` cloned ``hansen-m-recipes``) demanded a
third ancestor and failed local trust verification.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from automunki.services import trust as trust_module
from automunki.services.trust import (
    _recipe_tree_scan_patterns,
    _resolve_recipe,
    _resolve_recipe_in_tree,
)

# ── _recipe_tree_scan_patterns ──────────────────────────────────────────────


def test_zoom_download_path_matches_type_tier_not_name_tier() -> None:
    """``zoomus`` identifier vs ``Zoom.download.recipe`` on disk."""
    patterns = _recipe_tree_scan_patterns("zoomus", "download")
    path = "Zoom/Zoom.download.recipe"
    assert not patterns[0].search(path)
    assert patterns[1].search(path)


def test_firefox_download_path_matches_name_tier() -> None:
    patterns = _recipe_tree_scan_patterns("Firefox", "download")
    path = "Mozilla/Firefox.download.recipe"
    assert patterns[0].search(path)


# ── _resolve_recipe_in_tree ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_resolve_recipe_in_tree_finds_zoomus_by_identifier() -> None:
    tree = [{"type": "blob", "path": "Zoom/Zoom.download.recipe"}]
    recipe_data = {"Identifier": "com.github.hansen-m.download.zoomus"}

    with patch.object(trust_module, "_parse_recipe", AsyncMock(return_value=recipe_data)):
        resolved = await _resolve_recipe_in_tree(
            "autopkg/hansen-m-recipes",
            tree,
            "com.github.hansen-m.download.zoomus",
            "zoomus",
            "download",
        )

    assert resolved == ("autopkg/hansen-m-recipes", "Zoom/Zoom.download.recipe")


@pytest.mark.asyncio
async def test_resolve_recipe_in_tree_ignores_same_type_wrong_identifier() -> None:
    tree = [
        {"type": "blob", "path": "Zoom/Zoom.download.recipe"},
        {"type": "blob", "path": "Other/Other.download.recipe"},
    ]

    async def _fake_parse(repo: str, path: str) -> dict | None:
        if path.endswith("Zoom/Zoom.download.recipe"):
            return {"Identifier": "com.github.hansen-m.download.zoomus"}
        return {"Identifier": "com.example.download.other"}

    with patch.object(trust_module, "_parse_recipe", side_effect=_fake_parse):
        resolved = await _resolve_recipe_in_tree(
            "autopkg/hansen-m-recipes",
            tree,
            "com.github.hansen-m.download.zoomus",
            "zoomus",
            "download",
        )

    assert resolved == ("autopkg/hansen-m-recipes", "Zoom/Zoom.download.recipe")


# ── _resolve_recipe (integration with mocked GitHub) ─────────────────────────


@pytest.mark.asyncio
async def test_resolve_recipe_zoomus_via_hansen_m_repo() -> None:
    tree = [{"type": "blob", "path": "Zoom/Zoom.download.recipe"}]
    recipe_data = {"Identifier": "com.github.hansen-m.download.zoomus"}

    async def _tree_for_repo(repo: str, branch: str) -> list[dict]:
        if repo == "autopkg/hansen-m-recipes":
            return tree
        return []

    with (
        patch.object(trust_module, "_fetch_file_bytes", AsyncMock(return_value=None)),
        patch.object(trust_module, "_repo_default_branch", AsyncMock(return_value="master")),
        patch.object(trust_module, "_repo_tree", side_effect=_tree_for_repo),
        patch.object(trust_module, "_parse_recipe", AsyncMock(return_value=recipe_data)),
    ):
        resolved = await _resolve_recipe("com.github.hansen-m.download.zoomus")

    assert resolved == ("autopkg/hansen-m-recipes", "Zoom/Zoom.download.recipe")


# ── merge_db_trust_into_plist_for_runner ────────────────────────────────────


def test_merge_db_trust_replaces_stale_override_entries() -> None:
    plist = {
        "ParentRecipeTrustInfo": {
            "parent_recipes": {
                "com.github.hansen-m.download.zoom": {
                    "sha256_hash": "stale",
                    "git_hash": "",
                },
            },
            "non_core_processors": {
                "Zoom7zUnarchiver": {
                    "sha256_hash": "stale-proc",
                    "git_hash": "",
                },
            },
        },
    }
    trust_info = {
        "parent_recipes": {
            "com.github.homebysix.munki.Zoom": {"sha256_hash": "a"},
            "com.github.homebysix.pkg.Zoom": {"sha256_hash": "b"},
            "com.github.hansen-m.download.zoomus": {"sha256_hash": "c"},
        },
        "non_core_processors": {},
    }

    trust_module.merge_db_trust_into_plist_for_runner(plist, trust_info)

    parent = plist["ParentRecipeTrustInfo"]
    assert "com.github.hansen-m.download.zoom" not in parent["parent_recipes"]
    assert "com.github.hansen-m.download.zoomus" in parent["parent_recipes"]
    assert parent["non_core_processors"] == {}
