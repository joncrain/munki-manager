"""Merge ``AutoPkgRecipe.override_data.Input`` with ``input_variables`` for effective Input.

The UI and importers may store keys in either JSON column. The override plist (``override_data``)
is authoritative: for overlapping keys it wins. For ``Input.pkginfo``, both dicts are
deep-merged with the override's ``pkginfo`` keys winning so values like ``developer`` survive
when one side has a partial dict.

This module also provides :func:`substitute_input_vars` — a faithful port of
AutoPkg's ``autopkglib.update_data`` recursive ``%VAR%`` substitution. We need
it because AutoPkg substitutes Input variables when it runs the recipe on the
Mac (so the on-disk pkginfo has ``category = "Graphics & Rendering"``), but
when the backend re-merges the *raw* ``override_data.Input.pkginfo`` on top
during ingest, the override still contains the literal ``%MUNKI_CATEGORY%``
and would clobber AutoPkg's already-substituted value.
"""

from __future__ import annotations

import re
from typing import Any

from automunki.models.autopkg import AutoPkgRecipe

# Mirrors ``RE_KEYREF`` in autopkglib/__init__.py so we behave the same way
# AutoPkg does on disk.
_VAR_REF = re.compile(r"%(?P<key>[a-zA-Z_][a-zA-Z_0-9]*)%")


def substitute_input_vars(value: Any, lookup: dict[str, Any]) -> Any:
    """Recursively replace ``%KEY%`` references in ``value`` using ``lookup``.

    Behavior matches AutoPkg's ``update_data`` / ``do_variable_substitution``:

    * Strings have all ``%KEY%`` references replaced when ``KEY`` is in
      ``lookup``. Unknown keys are left as the literal ``%KEY%`` so we never
      overwrite an AutoPkg-runtime-substituted value (e.g. ``%pathname%``)
      with garbage.
    * Dicts and lists are recursed (returning new copies, not mutating
      input).
    * Non-string scalars pass through unchanged.

    Single-pass: if ``lookup[KEY]`` itself contains ``%VAR%``, it is *not*
    re-substituted, matching AutoPkg's single-pass behavior in
    ``process_cli_overrides``.
    """
    if isinstance(value, str):

        def _repl(m: re.Match[str]) -> str:
            key = m.group("key")
            if key in lookup:
                v = lookup[key]
                if isinstance(v, str):
                    return v
                if v is None:
                    return m.group(0)
                return str(v)
            return m.group(0)

        return _VAR_REF.sub(_repl, value)
    if isinstance(value, dict):
        return {k: substitute_input_vars(v, lookup) for k, v in value.items()}
    if isinstance(value, list):
        return [substitute_input_vars(item, lookup) for item in value]
    return value


def merged_recipe_input(recipe: AutoPkgRecipe) -> dict:
    """Return the effective ``Input`` dict for this recipe row (never None; may be empty)."""
    base: dict = {}
    if isinstance(recipe.input_variables, dict):
        base = dict(recipe.input_variables)

    od_in: dict | None = None
    if isinstance(recipe.override_data, dict):
        raw = recipe.override_data.get("Input")
        if isinstance(raw, dict):
            od_in = raw

    if not od_in:
        return base

    out = {**base, **od_in}
    ip = base.get("pkginfo")
    op = od_in.get("pkginfo")
    if isinstance(ip, dict) and isinstance(op, dict):
        out["pkginfo"] = {**ip, **op}
    elif op is not None:
        out["pkginfo"] = op
    elif ip is not None:
        out["pkginfo"] = ip
    return out
