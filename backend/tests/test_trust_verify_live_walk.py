"""Unit tests for the live-full-chain semantics of ``verify_trust``.

The bug these protect against: prior to the live-walk fix, ``verify_trust``
re-hashed *only the entries already stored* in ``trust_info`` and reported
``verified`` whenever those keys still matched. That silently masked three
production-impacting failure modes:

* **Missing ancestor** — UTM's grandparent
  ``com.github.ahousseini-recipes.download.UTM`` was never written into the
  user's stored trust info because identifier resolution silently failed
  during the original ``compute_trust_info``. AutoPkg-on-disk required
  that ancestor in ``ParentRecipeTrustInfo`` and refused to run; our verify
  reported ``verified`` and the user was told the recipe was good to go.
* **Modified grandparent** — any change in an ancestor recipe was
  undetectable because we never fetched that file.
* **Stale ancestor** — an upstream rename leaves the stored identifier
  pointing at a 404; AutoPkg fails the trust check, our verify silently
  keeps the stale entry as "verified".

Post-fix behaviour: ``verify_trust`` walks the live chain via
``compute_trust_info`` and diffs against stored. Any added / removed /
modified entry surfaces as ``status="failed"`` with a populated diff,
which ``persist_verify_trust_result`` then writes into a
``TrustChangeRequest`` so the operator must explicitly re-approve.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from automunki.services import trust as trust_module


@pytest.mark.asyncio
async def test_verify_returns_verified_when_full_chain_matches() -> None:
    """The trivial happy path: stored chain == live chain → ``verified``."""
    stored = {
        "parent_recipes": {
            "com.github.flammable.munki.UTM": {
                "sha256_hash": "abc",
                "github_repo": "autopkg/flammable-recipes",
                "github_path": "UTM/UTM.munki.recipe",
            },
        },
        "non_core_processors": {},
    }
    live = {
        "parent_recipes": {
            "com.github.flammable.munki.UTM": {
                "sha256_hash": "abc",
                "github_repo": "autopkg/flammable-recipes",
                "github_path": "UTM/UTM.munki.recipe",
            },
        },
        "non_core_processors": {},
    }

    async def _fake_compute(*args, **kwargs):
        return live

    with patch.object(trust_module, "compute_trust_info", _fake_compute):
        result = await trust_module.verify_trust(
            stored_trust_info=stored,
            parent_recipe_identifier="com.github.flammable.munki.UTM",
        )

    assert result.status == "verified"
    assert result.diff is None or result.diff == {}


@pytest.mark.asyncio
async def test_verify_flags_added_ancestor_as_failed() -> None:
    """The UTM-shaped bug: the live walk turned up a grandparent that is
    not in storage. The previous implementation reported ``verified``
    because re-hashing only walked stored keys; the new one reports
    ``failed`` with an ``added`` diff entry."""
    stored = {
        "parent_recipes": {
            "com.github.flammable.munki.UTM": {
                "sha256_hash": "abc",
                "github_repo": "autopkg/flammable-recipes",
                "github_path": "UTM/UTM.munki.recipe",
            },
        },
        "non_core_processors": {},
    }
    live = {
        "parent_recipes": {
            "com.github.flammable.munki.UTM": {
                "sha256_hash": "abc",
                "github_repo": "autopkg/flammable-recipes",
                "github_path": "UTM/UTM.munki.recipe",
            },
            "com.github.ahousseini-recipes.download.UTM": {
                "sha256_hash": "def",
                "github_repo": "autopkg/ahousseini-recipes",
                "github_path": "UTM/UTM.download.recipe",
            },
        },
        "non_core_processors": {},
    }

    async def _fake_compute(*args, **kwargs):
        return live

    with patch.object(trust_module, "compute_trust_info", _fake_compute):
        result = await trust_module.verify_trust(
            stored_trust_info=stored,
            parent_recipe_identifier="com.github.flammable.munki.UTM",
        )

    assert result.status == "failed"
    assert result.diff is not None
    parent_diff = result.diff["parent_recipes"]
    assert "com.github.ahousseini-recipes.download.UTM" in parent_diff
    assert parent_diff["com.github.ahousseini-recipes.download.UTM"]["change"] == "added"


@pytest.mark.asyncio
async def test_verify_flags_modified_grandparent() -> None:
    """A grandparent's content changed on GitHub. The legacy verify never
    fetched the grandparent (it wasn't ``stored_trust_info[parent_recipes]``'s
    immediate problem), so the change was invisible. The live walk picks
    it up."""
    stored = {
        "parent_recipes": {
            "com.github.flammable.munki.UTM": {
                "sha256_hash": "abc",
                "github_repo": "autopkg/flammable-recipes",
                "github_path": "UTM/UTM.munki.recipe",
            },
            "com.github.ahousseini-recipes.download.UTM": {
                "sha256_hash": "old-hash",
                "github_repo": "autopkg/ahousseini-recipes",
                "github_path": "UTM/UTM.download.recipe",
            },
        },
        "non_core_processors": {},
    }
    live = {
        "parent_recipes": {
            "com.github.flammable.munki.UTM": {
                "sha256_hash": "abc",
                "github_repo": "autopkg/flammable-recipes",
                "github_path": "UTM/UTM.munki.recipe",
            },
            "com.github.ahousseini-recipes.download.UTM": {
                "sha256_hash": "new-hash",
                "github_repo": "autopkg/ahousseini-recipes",
                "github_path": "UTM/UTM.download.recipe",
            },
        },
        "non_core_processors": {},
    }

    async def _fake_compute(*args, **kwargs):
        return live

    with patch.object(trust_module, "compute_trust_info", _fake_compute):
        result = await trust_module.verify_trust(
            stored_trust_info=stored,
            parent_recipe_identifier="com.github.flammable.munki.UTM",
        )

    assert result.status == "failed"
    parent_diff = result.diff["parent_recipes"]
    entry = parent_diff["com.github.ahousseini-recipes.download.UTM"]
    assert entry["change"] == "modified"
    assert entry["old_sha256"] == "old-hash"
    assert entry["new_sha256"] == "new-hash"


@pytest.mark.asyncio
async def test_verify_flags_stale_ancestor_as_not_found() -> None:
    """An upstream rename / delete: the stored identifier is no longer in
    the live chain (the live walker either didn't see it or couldn't
    resolve it). The diff surfaces this as ``not_found`` so the operator
    can clean up."""
    stored = {
        "parent_recipes": {
            "com.github.flammable.munki.UTM": {
                "sha256_hash": "abc",
                "github_repo": "autopkg/flammable-recipes",
                "github_path": "UTM/UTM.munki.recipe",
            },
            "com.github.dead.author.LegacyRecipe": {
                "sha256_hash": "stale",
                "github_repo": "autopkg/dead-recipes",
                "github_path": "Legacy/Legacy.recipe",
            },
        },
        "non_core_processors": {},
    }
    live = {
        "parent_recipes": {
            "com.github.flammable.munki.UTM": {
                "sha256_hash": "abc",
                "github_repo": "autopkg/flammable-recipes",
                "github_path": "UTM/UTM.munki.recipe",
            },
        },
        "non_core_processors": {},
    }

    async def _fake_compute(*args, **kwargs):
        return live

    with patch.object(trust_module, "compute_trust_info", _fake_compute):
        result = await trust_module.verify_trust(
            stored_trust_info=stored,
            parent_recipe_identifier="com.github.flammable.munki.UTM",
        )

    assert result.status == "failed"
    parent_diff = result.diff["parent_recipes"]
    assert parent_diff["com.github.dead.author.LegacyRecipe"]["change"] == "not_found"


@pytest.mark.asyncio
async def test_verify_returns_error_for_missing_inputs() -> None:
    """Pre-conditions still rejected so the route can return a clean 4xx."""
    no_trust = await trust_module.verify_trust(
        stored_trust_info=None,
        parent_recipe_identifier="anything",
    )
    assert no_trust.status == "error"
    assert no_trust.error and "no trust info" in no_trust.error.lower()

    no_parent = await trust_module.verify_trust(
        stored_trust_info={"parent_recipes": {}, "non_core_processors": {}},
        parent_recipe_identifier=None,
    )
    assert no_parent.status == "error"
    assert no_parent.error and "no parent recipe" in no_parent.error.lower()


@pytest.mark.asyncio
async def test_verify_falls_back_to_stored_rehash_on_resolver_failure() -> None:
    """Defense in depth: if the live walker raises (e.g. transient GitHub
    error that isn't 403/429), we should not flip a previously-approved
    recipe to ``failed`` solely because GitHub blipped. We fall back to
    re-hashing the stored entries (legacy behaviour) which still catches
    sha256 changes on the entries we already have."""
    stored = {
        "parent_recipes": {
            "com.github.flammable.munki.UTM": {
                "sha256_hash": "abc",
                "github_repo": "autopkg/flammable-recipes",
                "github_path": "UTM/UTM.munki.recipe",
            },
        },
        "non_core_processors": {},
    }
    rehashed = {
        "parent_recipes": {
            "com.github.flammable.munki.UTM": {"sha256_hash": "abc"},
        },
        "non_core_processors": {},
    }

    async def _explode(*args, **kwargs):
        raise RuntimeError("transient github connection reset")

    async def _fake_rehash(stored_trust_info: dict) -> dict:
        return rehashed

    with (
        patch.object(trust_module, "compute_trust_info", _explode),
        patch.object(trust_module, "_compute_current_hashes", _fake_rehash),
    ):
        result = await trust_module.verify_trust(
            stored_trust_info=stored,
            parent_recipe_identifier="com.github.flammable.munki.UTM",
        )

    assert result.status == "verified"


@pytest.mark.asyncio
async def test_verify_propagates_rate_limit_from_live_walker() -> None:
    """Rate-limit errors must short-circuit verification (no fall-back)
    so callers can degrade and surface the GitHub message."""

    async def _rate_limited(*args, **kwargs):
        raise trust_module.GitHubRateLimitError("rate limit exceeded")

    with patch.object(trust_module, "compute_trust_info", _rate_limited):
        result = await trust_module.verify_trust(
            stored_trust_info={
                "parent_recipes": {"x": {"sha256_hash": "y"}},
                "non_core_processors": {},
            },
            parent_recipe_identifier="x",
        )

    assert result.status == "error"
    assert result.error and "rate limit" in result.error.lower()


@pytest.mark.asyncio
async def test_verify_propagates_github_forbidden_with_message() -> None:
    """403-not-rate-limit must surface GitHub's message (e.g. PAT lifetime
    policy on the autopkg org) instead of being misclassified as a rate
    limit."""
    forbidden = trust_module.GitHubForbiddenError(
        message="Personal access tokens with fine-grained access...",
    )

    async def _forbidden(*args, **kwargs):
        raise forbidden

    with patch.object(trust_module, "compute_trust_info", _forbidden):
        result = await trust_module.verify_trust(
            stored_trust_info={
                "parent_recipes": {"x": {"sha256_hash": "y"}},
                "non_core_processors": {},
            },
            parent_recipe_identifier="x",
        )

    assert result.status == "error"
    assert result.error and "github denied access" in result.error.lower()
    assert result.error and "fine-grained access" in result.error
