"""Unit tests for identifier-resolution helpers in ``services.trust``.

These pure helpers feed the recipe-chain walker (``compute_trust_info``) and
the repo-inference for ``run_repo_list.txt`` (``infer_repos_from_trust_info``).
Both used to only understand identifiers prefixed with ``com.github.`` or
``io.github.``; recipes from authors like scriptingosx / mosen use the short
``com.<author>.<type>.<name>`` form and silently fell out, leaving trust info
incomplete for any chain that went through them. AutoPkg's local trust check
then fails because it walks the on-disk chain and demands every ancestor be
in ``ParentRecipeTrustInfo``; meanwhile the backend's ``verify_trust`` only
re-hashes the entries that *are* stored and reports "verified" — a false
positive.
"""

from __future__ import annotations

import pytest

from automunki.services.trust import (
    _candidate_repos,
    _parse_identifier,
    _repo_from_identifier,
    infer_repos_from_trust_info,
)

# ── _parse_identifier ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "identifier,expected",
    [
        # Long form com.github.autopkg.<user>.<type>.<name>
        (
            "com.github.autopkg.wardsparadox.munki.Ghostty",
            ("wardsparadox", "munki", "Ghostty"),
        ),
        # com.github.<user>.<type>.<name> (no autopkg in middle)
        (
            "com.github.swy.download.BraveUniversal",
            ("swy", "download", "BraveUniversal"),
        ),
        # io.github variants
        (
            "io.github.hjuutilainen.munki.Blender",
            ("hjuutilainen", "munki", "Blender"),
        ),
        # Short form com.<author>.<type>.<name> — the WhatsApp case.
        (
            "com.scriptingosx.munki.WhatsApp",
            ("scriptingosx", "munki", "WhatsApp"),
        ),
        # Same author, different recipe type (the broken chain parent).
        (
            "com.scriptingosx.download.WhatsApp",
            ("scriptingosx", "download", "WhatsApp"),
        ),
        # mosen, another common short-form author.
        (
            "com.mosen.pkg.AdobeAcrobatPro",
            ("mosen", "pkg", "AdobeAcrobatPro"),
        ),
    ],
)
def test_parse_identifier_known_forms(identifier: str, expected: tuple[str, str, str]) -> None:
    assert _parse_identifier(identifier) == expected


def test_parse_identifier_does_not_misparse_explicit_com_github() -> None:
    """The short-form regex must not consume ``com.github.*`` identifiers.

    If it did, ``com.github.autopkg.<user>.<type>.<name>`` would parse as
    ``author=github``, which would route resolution at ``autopkg/github-recipes``
    (nonexistent) instead of ``autopkg/<user>-recipes``.
    """
    parsed = _parse_identifier("com.github.autopkg.wardsparadox.munki.Ghostty")
    assert parsed is not None
    assert parsed[0] != "github"


def test_parse_identifier_garbage_returns_none() -> None:
    # Short-form regex anchors at literal ``com.`` so anything else falls through.
    assert _parse_identifier("not.an.autopkg.id.maybe") is None
    assert _parse_identifier("nodots") is None
    assert _parse_identifier("two.parts") is None
    assert _parse_identifier("three.parts.here") is None


# ── _candidate_repos ────────────────────────────────────────────────────────


def test_candidate_repos_long_form_scriptingosx_via_github_autopkg() -> None:
    repos = _candidate_repos("com.github.autopkg.scriptingosx.munki.WhatsApp")
    assert "autopkg/scriptingosx-recipes" in repos


def test_candidate_repos_short_form_maps_to_author_recipes() -> None:
    """The fix: short form must route to ``autopkg/<author>-recipes``.

    Before the fix this returned only ``["autopkg/recipes"]`` and
    ``_resolve_recipe`` then failed to find scriptingosx recipes in
    ``autopkg/recipes`` — leaving the chain ancestor un-hashed and the
    override missing a trust entry.
    """
    repos = _candidate_repos("com.scriptingosx.download.WhatsApp")
    assert repos[0] == "autopkg/scriptingosx-recipes"
    assert "autopkg/recipes" in repos  # still a fallback


def test_candidate_repos_short_form_with_different_author() -> None:
    repos = _candidate_repos("com.mosen.pkg.AdobeAcrobatPro")
    assert repos[0] == "autopkg/mosen-recipes"


def test_candidate_repos_unrecognized_falls_back_to_autopkg_recipes() -> None:
    assert _candidate_repos("totally.unrelated") == ["autopkg/recipes"]


def test_candidate_repos_short_form_skips_com_github_misparse() -> None:
    """``com.github.X.Y.Z`` must not fall through to the short-form branch.

    The guard in ``_candidate_repos`` ignores ``com.github.*`` so the
    explicit-form regex above handles it instead. Without the guard,
    ``com.github.autopkg.scriptingosx.munki.WhatsApp`` would yield
    ``author="github"`` → ``autopkg/github-recipes``.
    """
    repos = _candidate_repos("com.github.autopkg.scriptingosx.munki.WhatsApp")
    assert "autopkg/github-recipes" not in repos


def test_candidate_repos_org_segment_already_ends_in_recipes() -> None:
    """UTM grandparent: ``com.github.ahousseini-recipes.download.UTM``.

    The author baked ``-recipes`` into the reverse-DNS prefix. Without
    the special case, candidates were ``autopkg/download-recipes`` (wrong
    repo) and ``autopkg/ahousseini-recipes-recipes`` (does not exist) —
    the chain walker fetched nothing and ``infer_repos_from_trust_info``
    silently dropped the repo from ``run_repo_list.txt``, so AutoPkg's
    runtime parent-recipe lookup failed.
    """
    repos = _candidate_repos("com.github.ahousseini-recipes.download.UTM")
    assert repos[0] == "autopkg/ahousseini-recipes"
    assert "autopkg/ahousseini-recipes-recipes" not in repos


# ── _repo_from_identifier ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    "identifier,expected",
    [
        (
            "com.github.autopkg.wardsparadox.munki.Ghostty",
            "autopkg/wardsparadox-recipes",
        ),
        # ``com.github.<user>.<type>.<name>`` — same convention without the
        # explicit ``autopkg`` middle segment.
        (
            "com.github.swy.download.BraveUniversal",
            "autopkg/swy-recipes",
        ),
        # Short form — the WhatsApp case. Drives what shows up in
        # ``run_repo_list.txt`` via ``infer_repos_from_trust_info``.
        (
            "com.scriptingosx.munki.WhatsApp",
            "autopkg/scriptingosx-recipes",
        ),
        (
            "com.mosen.pkg.AdobeAcrobatPro",
            "autopkg/mosen-recipes",
        ),
        # UTM grandparent: middle segment already ends in ``-recipes``.
        # Don't double-suffix; the segment IS the repo name.
        (
            "com.github.ahousseini-recipes.download.UTM",
            "autopkg/ahousseini-recipes",
        ),
    ],
)
def test_repo_from_identifier_known_forms(identifier: str, expected: str) -> None:
    assert _repo_from_identifier(identifier) == expected


def test_repo_from_identifier_explicit_takes_precedence_over_short() -> None:
    """``com.github.autopkg.<user>.<type>.<name>`` must NOT trip the short-form
    branch (which would map ``author=github`` → ``autopkg/github-recipes``).
    """
    repo = _repo_from_identifier("com.github.autopkg.wardsparadox.munki.Ghostty")
    assert repo == "autopkg/wardsparadox-recipes"


def test_repo_from_identifier_unknown_returns_none() -> None:
    assert _repo_from_identifier("nothing") is None
    assert _repo_from_identifier("two.parts") is None


# ── infer_repos_from_trust_info ────────────────────────────────────────────


def test_infer_repos_from_trust_info_short_form_identifier() -> None:
    """End-to-end check: a trust_info entry whose key is the short-form
    ``com.scriptingosx.*`` identifier produces ``autopkg/scriptingosx-recipes``
    in ``run_repo_list.txt`` even when the entry itself lacks an explicit
    ``github_repo`` field (e.g. legacy overrides imported before the chain
    walker populated locations).
    """
    trust_info = {
        "parent_recipes": {
            "com.scriptingosx.munki.WhatsApp": {
                "sha256_hash": "abc123",
                # Note: no github_repo / github_path here.
            },
        },
        "non_core_processors": {},
    }
    repos = infer_repos_from_trust_info(trust_info)
    assert "autopkg/scriptingosx-recipes" in repos


def test_infer_repos_from_trust_info_prefers_explicit_github_repo() -> None:
    """When an entry already carries ``github_repo``, that wins over inference.

    This is the normal case for trust_info computed by ``compute_trust_info``
    — every entry has explicit ``github_repo``/``github_path``. We want to
    use those verbatim and not re-infer (the explicit value is canonical).
    """
    trust_info = {
        "parent_recipes": {
            "com.scriptingosx.munki.WhatsApp": {
                "sha256_hash": "abc123",
                "github_repo": "scriptingosx/personal-recipes",
                "github_path": "WhatsApp/WhatsApp.munki.recipe",
            },
        },
        "non_core_processors": {},
    }
    repos = infer_repos_from_trust_info(trust_info)
    assert "scriptingosx/personal-recipes" in repos
    # Don't double-add the inferred repo when an explicit one exists.
    assert "autopkg/scriptingosx-recipes" not in repos


def test_infer_repos_from_trust_info_mixed_chain() -> None:
    """Common shape post-fix: a chain that spans the short and long forms.

    E.g. ``com.scriptingosx.munki.WhatsApp`` (short, repo from inference) and
    ``com.github.autopkg.recipes.shared.SomeProcessor`` (long, repo from
    inference). Both repos should land in ``run_repo_list.txt``.
    """
    trust_info = {
        "parent_recipes": {
            "com.scriptingosx.munki.WhatsApp": {"sha256_hash": "a"},
            "com.scriptingosx.download.WhatsApp": {"sha256_hash": "b"},
        },
        "non_core_processors": {
            "com.github.autopkg.wardsparadox.munki.SomeProc": {"sha256_hash": "c"},
        },
    }
    repos = infer_repos_from_trust_info(trust_info)
    assert "autopkg/scriptingosx-recipes" in repos
    assert "autopkg/wardsparadox-recipes" in repos


def test_infer_repos_from_trust_info_empty_or_none() -> None:
    assert infer_repos_from_trust_info(None) == []
    assert infer_repos_from_trust_info({}) == []
    assert infer_repos_from_trust_info({"parent_recipes": {}, "non_core_processors": {}}) == []


def test_infer_repos_from_trust_info_utm_full_chain() -> None:
    """UTM full chain: ``flammable.munki`` → ``ahousseini-recipes.download``.

    Reproduces the parent-resolution failure: when the chain walker
    correctly records both ancestors (post the ``compute_trust_info``
    fix that walks the full chain), the repo inferer must produce both
    ``autopkg/flammable-recipes`` and ``autopkg/ahousseini-recipes`` so
    ``run_repo_list.txt`` covers the whole chain.
    """
    trust_info = {
        "parent_recipes": {
            "com.github.flammable.munki.UTM": {"sha256_hash": "a"},
            "com.github.ahousseini-recipes.download.UTM": {"sha256_hash": "b"},
        },
        "non_core_processors": {},
    }
    repos = infer_repos_from_trust_info(trust_info)
    assert "autopkg/flammable-recipes" in repos
    assert "autopkg/ahousseini-recipes" in repos
    assert "autopkg/ahousseini-recipes-recipes" not in repos
