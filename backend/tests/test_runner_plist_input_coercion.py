"""Runner plist coerces non-string ``Input`` scalars to strings.

Pins the contract that ``_runner_plist_dict_for_recipe`` emits AutoPkg-safe
plist Input values. Without this, the override editor's ``kvToDict``
(``JSON.parse`` per entry) silently promotes scalar entries — ``"5"`` →
``5`` (int), ``"true"`` → ``True`` (bool) — and the resulting plist breaks
AutoPkg the moment the upper-case ``%VAR%`` is interpolated into a
``<string>`` template:

* ``Blender.download.recipe`` ``re_pattern`` references ``%MAJOR_VERSION%``
  → ``TypeError: sequence item 1: expected str instance, int found``.
* ``Cursor.munki.recipe`` ``derive_minimum_os_version`` references
  ``%DERIVE_MIN_OS%`` → ``TypeError: sequence item 0: expected str
  instance, bool found``.

Per the AutoPkg wiki convention (Variables / Input Variables), upper-case
Input keys carry strings used in ``%VAR%`` substitution; lower-case keys
(``extract_icon``, ``pkginfo``, ``catalogs``, …) carry native types.
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


def test_coerce_helper_preserves_lowercase_bools() -> None:
    # Lower-case keys carry native types per the AutoPkg wiki convention
    # (``extract_icon`` is consumed natively by MunkiImporter, never
    # interpolated). ``bool`` is a subclass of ``int`` so the bool branch
    # must be checked before the int branch.
    out = _coerce_input_scalars_to_str({"extract_icon": True, "unattended_install": False})
    assert out == {"extract_icon": True, "unattended_install": False}


def test_coerce_helper_converts_uppercase_bool_to_str() -> None:
    # ``Cursor.munki.recipe`` declares ``DERIVE_MIN_OS`` as a string
    # ``"true"`` and templates ``%DERIVE_MIN_OS%`` into the
    # ``MunkiInstallsItemsCreator.derive_minimum_os_version`` argument.
    # JSON storage promoting ``"true"`` to ``True`` would crash AutoPkg's
    # ``RE_KEYREF.sub(getdata, item)`` when it tries to substitute a bool
    # into the ``<string>`` template.
    out = _coerce_input_scalars_to_str({"DERIVE_MIN_OS": True, "DEBUG": False})
    assert out == {"DERIVE_MIN_OS": "true", "DEBUG": "false"}


def test_coerce_helper_preserves_uppercase_strings() -> None:
    # Upper-case keys whose value is already a string must pass through
    # unchanged — coercion is only for non-string scalars.
    out = _coerce_input_scalars_to_str({"DERIVE_MIN_OS": "true", "NAME": "Cursor"})
    assert out == {"DERIVE_MIN_OS": "true", "NAME": "Cursor"}


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
    # ``_apply_extract_icon_to_runner_plist`` injects ``extract_icon=True``;
    # coercion must not flatten the lower-case key to ``"true"``.
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


def test_runner_plist_coerces_uppercase_bool_input_var() -> None:
    # Reproduces the Cursor.munki crash: ``DERIVE_MIN_OS`` stored as
    # bool ``True`` in the override (after JSON.parse promotion in the
    # editor) would emit ``<true/>`` in the plist; AutoPkg's
    # ``do_variable_substitution`` then crashes when
    # ``MunkiInstallsItemsCreator.derive_minimum_os_version =
    # "%DERIVE_MIN_OS%"`` is evaluated.
    recipe = _make_recipe(
        identifier="local.munki.Cursor",
        name="Cursor.munki",
        parent_recipe="com.github.peetinc.munki.Cursor",
        override_data={
            "Identifier": "local.munki.Cursor",
            "ParentRecipe": "com.github.peetinc.munki.Cursor",
            "Input": {
                "NAME": "Cursor",
                "DERIVE_MIN_OS": True,
                "MUNKI_CATEGORY": "Developer",
            },
        },
    )
    plist = _runner_plist_dict_for_recipe(recipe)
    assert plist["Input"]["DERIVE_MIN_OS"] == "true"
    assert plist["Input"]["NAME"] == "Cursor"
    assert plist["Input"]["MUNKI_CATEGORY"] == "Developer"
