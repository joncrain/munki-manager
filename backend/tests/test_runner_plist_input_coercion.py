"""Runner plist coerces numeric ``Input`` scalars to strings.

Pins the contract that ``_runner_plist_dict_for_recipe`` emits AutoPkg-safe
plist Input values. Without this, the override editor's ``kvToDict``
(``JSON.parse`` per entry) silently promotes ``"5"`` to a JSON number; the
runner serializes ``<integer>5</integer>``; AutoPkg's
``do_variable_substitution`` (``RE_KEYREF.sub(getdata, item)``) then crashes
with ``TypeError: sequence item 1: expected str instance, int found`` the
moment that variable is referenced inside a string template (e.g.
``re_pattern = "(?s)(Blender(%MAJOR_VERSION%\\.\\d+)/)..."`` in
``Blender.download.recipe``).
"""

from __future__ import annotations

from automunki.api.routes.autopkg import (
    _coerce_input_scalars_to_str,
    _runner_plist_dict_for_recipe,
)
from automunki.models.autopkg import AutoPkgRecipe


def _make_recipe(**kwargs) -> AutoPkgRecipe:
    """Minimal in-memory recipe — never committed to the DB."""
    recipe = AutoPkgRecipe(
        identifier=kwargs.get("identifier", "local.munki.Blender"),
        name=kwargs.get("name", "Blender.munki"),
        parent_recipe=kwargs.get("parent_recipe", "io.github.hjuutilainen.munki.Blender"),
    )
    recipe.is_enabled = True
    recipe.extract_icon_enabled = kwargs.get("extract_icon_enabled", False)
    recipe.auto_promote = False
    recipe.trust_status = "unknown"
    recipe.override_data = kwargs.get("override_data")
    recipe.trust_info = kwargs.get("trust_info")
    recipe.input_variables = kwargs.get("input_variables")
    return recipe


def test_coerce_helper_converts_int_to_str() -> None:
    out = _coerce_input_scalars_to_str({"MAJOR_VERSION": 5, "NAME": "Blender"})
    assert out == {"MAJOR_VERSION": "5", "NAME": "Blender"}


def test_coerce_helper_converts_float_to_str() -> None:
    out = _coerce_input_scalars_to_str({"MIN_VERSION": 4.5})
    assert out == {"MIN_VERSION": "4.5"}


def test_coerce_helper_preserves_bools() -> None:
    # ``bool`` is a subclass of ``int`` — must be checked before ``int``.
    out = _coerce_input_scalars_to_str({"extract_icon": True, "unattended_install": False})
    assert out == {"extract_icon": True, "unattended_install": False}


def test_coerce_helper_preserves_none() -> None:
    out = _coerce_input_scalars_to_str({"WHATEVER": None})
    assert out == {"WHATEVER": None}


def test_coerce_helper_preserves_nested_structures() -> None:
    pkginfo = {"category": "Graphics", "version": 5}
    catalogs = ["testing", "production"]
    out = _coerce_input_scalars_to_str({"pkginfo": pkginfo, "catalogs": catalogs})
    # Nested ``int`` inside ``pkginfo`` is intentionally left alone — only
    # top-level ``Input`` scalars are AutoPkg's substitution-time concern.
    assert out["pkginfo"] is pkginfo
    assert out["catalogs"] is catalogs


def test_runner_plist_coerces_int_input_var_via_override_data() -> None:
    recipe = _make_recipe(
        override_data={
            "Identifier": "local.munki.Blender",
            "ParentRecipe": "io.github.hjuutilainen.munki.Blender",
            "Input": {
                "NAME": "Blender",
                "ARCHITECTURE": "arm64",
                # The bug: JSON storage promoted ``"5"`` -> ``5``.
                "MAJOR_VERSION": 5,
            },
        },
    )
    plist = _runner_plist_dict_for_recipe(recipe)
    assert plist["Input"]["MAJOR_VERSION"] == "5"
    assert plist["Input"]["NAME"] == "Blender"
    assert plist["Input"]["ARCHITECTURE"] == "arm64"


def test_runner_plist_coerces_int_input_var_via_input_variables_only() -> None:
    # Recipes without ``override_data`` (loose ``input_variables`` only) also
    # need the same defense.
    recipe = _make_recipe(
        override_data=None,
        input_variables={"MAJOR_VERSION": 5, "NAME": "Blender"},
    )
    plist = _runner_plist_dict_for_recipe(recipe)
    assert plist["Input"]["MAJOR_VERSION"] == "5"
    assert plist["Input"]["NAME"] == "Blender"


def test_runner_plist_preserves_extract_icon_bool() -> None:
    # ``_apply_extract_icon_to_runner_plist`` injects ``True``; coercion
    # must not flatten that to the string ``"True"``.
    recipe = _make_recipe(
        extract_icon_enabled=True,
        override_data={
            "Identifier": "local.munki.Blender",
            "ParentRecipe": "io.github.hjuutilainen.munki.Blender",
            "Input": {"NAME": "Blender"},
        },
    )
    plist = _runner_plist_dict_for_recipe(recipe)
    assert plist["Input"]["extract_icon"] is True
