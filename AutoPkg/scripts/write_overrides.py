"""Read run_config.json and write override plists, recipe list, and repo list."""

import json
import os
import plistlib
from typing import Any


def _coerce_input_scalars_to_str(inp: dict) -> dict:
    """Coerce numeric ``Input`` scalars to strings before serializing.

    AutoPkg Input values are conventionally strings in upstream recipes
    (e.g. ``MAJOR_VERSION = "5"`` in ``Blender.download.recipe``). JSON
    storage and the override editor's ``kvToDict`` (``JSON.parse`` per
    entry) can promote ``"5"`` to a JSON number. ``plistlib.dump`` then
    writes it as ``<integer>5</integer>``, and AutoPkg's
    ``do_variable_substitution`` (``RE_KEYREF.sub(getdata, item)``) crashes
    with ``TypeError: sequence item 1: expected str instance, int found``
    the moment that variable is referenced inside a string template (e.g.
    ``re_pattern = "(?s)(Blender(%MAJOR_VERSION%\\.\\d+)/)..."``).

    Runner-side defense so we don't depend on every backend deployment
    having the matching server-side fix. The backend applies the same
    coercion in ``_runner_plist_dict_for_recipe``; this keeps a runner
    from emitting a broken plist if it happens to talk to an older server.

    Bools (``extract_icon``, ``unattended_install``, …), ``None``, dicts
    (``pkginfo``), and lists (``catalogs``) are left alone. ``bool`` is a
    subclass of ``int`` in Python, so it is checked first.
    """
    out: dict[str, Any] = {}
    for k, v in inp.items():
        if isinstance(v, bool) or v is None:
            out[k] = v
        elif isinstance(v, (int, float)):
            out[k] = str(v)
        else:
            out[k] = v
    return out


with open("run_config.json") as f:
    config = json.load(f)

override_dir = os.path.join(os.environ["GITHUB_WORKSPACE"], "AutoPkg", "Overrides")
os.makedirs(override_dir, exist_ok=True)

recipe_names: list[str] = []
for override in config.get("overrides", []):
    name = override["name"]
    plist_data = override.get("plist", {})
    if isinstance(plist_data, dict) and isinstance(plist_data.get("Input"), dict):
        plist_data["Input"] = _coerce_input_scalars_to_str(plist_data["Input"])
    filename = f"{name}.munki.recipe"
    filepath = os.path.join(override_dir, filename)

    with open(filepath, "wb") as f:
        plistlib.dump(plist_data, f)
    print(f"Wrote override: {filepath}")
    recipe_names.append(filename)

with open("AutoPkg/run_recipe_list.json", "w") as f:
    json.dump(recipe_names, f)
print(f"Recipe list: {recipe_names}")

repos = config.get("repos", [])
with open("AutoPkg/run_repo_list.txt", "w") as f:
    for repo in repos:
        f.write(repo + "\n")
print(f"Repo list ({len(repos)} repos): {repos}")
