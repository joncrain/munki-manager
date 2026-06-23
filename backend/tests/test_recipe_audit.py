"""Audit snapshots for AutoPkg recipe updates."""

from __future__ import annotations

from automunki.api.routes.autopkg import _recipe_audit_snapshot
from automunki.models.autopkg import AutoPkgRecipe


def _make_recipe(**kwargs) -> AutoPkgRecipe:
    recipe = AutoPkgRecipe(
        identifier=kwargs.get("identifier", "local.munki.Example"),
        name=kwargs.get("name", "Example.munki"),
        parent_recipe=kwargs.get("parent_recipe", "io.github.example.munki.Example"),
    )
    recipe.is_enabled = kwargs.get("is_enabled", True)
    recipe.extract_icon_enabled = kwargs.get("extract_icon_enabled", False)
    recipe.auto_promote = kwargs.get("auto_promote", False)
    recipe.trust_status = kwargs.get("trust_status", "unknown")
    recipe.override_data = kwargs.get("override_data")
    recipe.trust_info = kwargs.get("trust_info")
    recipe.input_variables = kwargs.get("input_variables")
    recipe.source_repo_full_name = kwargs.get("source_repo_full_name")
    return recipe


def test_recipe_audit_snapshot_captures_editable_fields() -> None:
    recipe = _make_recipe(
        input_variables={"NAME": "Example", "MUNKI_REPO_SUBDIR": "apps"},
        override_data={"Identifier": "local.munki.Example", "Input": {"NAME": "Example"}},
    )

    snap = _recipe_audit_snapshot(recipe)

    assert snap["identifier"] == "local.munki.Example"
    assert snap["name"] == "Example.munki"
    assert snap["input_variables"] == {"NAME": "Example", "MUNKI_REPO_SUBDIR": "apps"}
    assert snap["override_data"]["Identifier"] == "local.munki.Example"


def test_recipe_audit_snapshot_reflects_mutation() -> None:
    recipe = _make_recipe(input_variables={"NAME": "Before"})
    before = _recipe_audit_snapshot(recipe)

    recipe.input_variables = {"NAME": "After"}
    after = _recipe_audit_snapshot(recipe)

    assert before["input_variables"] == {"NAME": "Before"}
    assert after["input_variables"] == {"NAME": "After"}
