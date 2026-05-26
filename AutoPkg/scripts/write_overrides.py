"""Read run_config.json and write override plists, recipe list, and repo list."""

import json
import os
import plistlib
import re
from typing import Any

_UPPER_INPUT_KEY = re.compile(r"^[A-Z_][A-Z0-9_]*$")


def _coerce_input_scalars_to_str(inp: dict) -> dict:
    """Coerce non-string ``Input`` scalars to strings before serializing.

    Runner-side defense mirroring the backend's ``_coerce_input_scalars_to_str``
    in ``backend/automunki/api/routes/autopkg.py`` — see that module's docstring
    for the full rationale and the two known crash sites
    (``Blender.download`` ``MAJOR_VERSION`` int, ``Cursor.munki``
    ``DERIVE_MIN_OS`` bool). Keeping this in lockstep means a runner can't
    emit a broken plist even if it talks to an older server build that
    hasn't received the matching coercion.

    Strategy: for top-level Input keys matching AutoPkg's upper-case
    substitution convention, coerce ``int``/``float``/``bool`` to their
    string form. Lower-case keys (``extract_icon``, ``unattended_install``,
    …), dicts, lists, and ``None`` are left alone. ``bool`` is a subclass
    of ``int`` so it is checked first.
    """
    out: dict[str, Any] = {}
    for k, v in inp.items():
        if v is None or isinstance(v, (dict, list)):
            out[k] = v
            continue
        is_substitution_key = isinstance(k, str) and bool(_UPPER_INPUT_KEY.match(k))
        if isinstance(v, bool):
            out[k] = ("true" if v else "false") if is_substitution_key else v
        elif isinstance(v, (int, float)):
            out[k] = str(v) if is_substitution_key else v
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
