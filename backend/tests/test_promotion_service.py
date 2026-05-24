"""Promotion channel helpers."""

from types import SimpleNamespace

from automunki.services.promotion import recipe_pkginfo_name_key


def test_recipe_pkginfo_name_key_uses_input_name():
    recipe = SimpleNamespace(
        name="Firefox.munki",
        override_data={"Input": {"NAME": "Firefox"}},
        input_variables=None,
    )
    assert recipe_pkginfo_name_key(recipe) == "Firefox"


def test_recipe_pkginfo_name_key_falls_back_to_recipe_name():
    recipe = SimpleNamespace(
        name="Something",
        override_data=None,
        input_variables={},
    )
    assert recipe_pkginfo_name_key(recipe) == "Something"
