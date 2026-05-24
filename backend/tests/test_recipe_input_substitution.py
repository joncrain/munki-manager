"""``substitute_input_vars`` mirrors AutoPkg's ``%VAR%`` substitution.

These tests pin the behavior described in the module docstring — without
them, regressions silently re-introduce the ``category = "%MUNKI_CATEGORY%"``
bug where the override's literal ``%VAR%`` clobbers AutoPkg's already-
substituted on-disk pkginfo during ingest.
"""

from __future__ import annotations

from automunki.services.recipe_input_merge import substitute_input_vars


def test_substitutes_known_var_in_string() -> None:
    out = substitute_input_vars("%NAME%", {"NAME": "Blender"})
    assert out == "Blender"


def test_leaves_unknown_var_as_literal() -> None:
    # AutoPkg ``log_err`` on this; we silently leave it so we never
    # clobber runtime-substituted values (e.g. ``%pathname%``).
    out = substitute_input_vars("%pathname%", {"NAME": "Blender"})
    assert out == "%pathname%"


def test_substitutes_within_text() -> None:
    out = substitute_input_vars("apps/%NAME%/install", {"NAME": "Blender"})
    assert out == "apps/Blender/install"


def test_recurses_into_dicts() -> None:
    inp = {"category": "%MUNKI_CATEGORY%", "name": "%NAME%"}
    out = substitute_input_vars(inp, {"NAME": "Blender", "MUNKI_CATEGORY": "Graphics & Rendering"})
    assert out == {"category": "Graphics & Rendering", "name": "Blender"}
    # Does not mutate the input.
    assert inp == {"category": "%MUNKI_CATEGORY%", "name": "%NAME%"}


def test_recurses_into_nested_lists_and_dicts() -> None:
    inp = {
        "catalogs": ["%CATALOG%", "production"],
        "pkginfo": {"display_name": "%NAME%"},
    }
    out = substitute_input_vars(inp, {"CATALOG": "testing", "NAME": "Blender"})
    assert out == {
        "catalogs": ["testing", "production"],
        "pkginfo": {"display_name": "Blender"},
    }


def test_non_string_scalars_pass_through() -> None:
    assert substitute_input_vars(True, {}) is True
    assert substitute_input_vars(42, {}) == 42
    assert substitute_input_vars(None, {}) is None


def test_single_pass_does_not_chain() -> None:
    # AutoPkg's process_cli_overrides is single-pass per string; if a lookup
    # value itself contains ``%VAR%`` we do not re-substitute. Pin that.
    out = substitute_input_vars("%A%", {"A": "%B%", "B": "value"})
    assert out == "%B%"


def test_blender_recipe_pkginfo_substitutes_category_and_name() -> None:
    # End-to-end shape of the override pkginfo for the Blender recipe.
    pkginfo = {
        "catalogs": ["testing"],
        "category": "%MUNKI_CATEGORY%",
        "description": "Blender is the open source...",
        "developer": "The Blender Foundation",
        "display_name": "Blender",
        "name": "%NAME%",
        "unattended_install": True,
    }
    lookup = {
        "NAME": "Blender",
        "MUNKI_CATEGORY": "Graphics & Rendering",
        "MUNKI_REPO_SUBDIR": "apps/%NAME%",  # not used here
    }
    out = substitute_input_vars(pkginfo, lookup)
    assert out["category"] == "Graphics & Rendering"
    assert out["name"] == "Blender"
    assert out["unattended_install"] is True
    assert out["developer"] == "The Blender Foundation"
