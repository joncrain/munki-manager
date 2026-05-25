"""Tests for ``AutoPkg/scripts/load_metadata_cache.py``.

The script is loaded by absolute path so this test file doesn't depend on
the backend's ``automunki`` package or any ``sys.path`` gymnastics. Running
the file with ``python3 path/to/load_metadata_cache.py`` still does the
right thing thanks to the ``__name__ == "__main__"`` guard added alongside
this test; importing it (which is what ``importlib.util`` does here) just
exposes the helpers.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "load_metadata_cache.py"
_spec = importlib.util.spec_from_file_location("_load_metadata_cache", _SCRIPT)
assert _spec is not None and _spec.loader is not None
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def test_rewrites_placeholder_to_current_workspace():
    out = mod._rewrite_file_path(
        "${WORKSPACE}/AutoPkg/Cache/local.munki.Foo/downloads/foo.zip",
        workspace="/Users/runner/work/munki-manager/munki-manager",
    )
    assert (
        out
        == "/Users/runner/work/munki-manager/munki-manager/AutoPkg/Cache/local.munki.Foo/downloads/foo.zip"
    )


def test_rewrites_legacy_mac_mini_path_to_current_workspace():
    # This is the exact bug from production run 26381404629: a Mac mini saved
    # /opt/UnitySrc/.../AutoPkg/Cache/... and the next GHA runner needed it
    # rewritten to /Users/runner/work/.../AutoPkg/Cache/... or it crashed.
    out = mod._rewrite_file_path(
        "/opt/UnitySrc/joncrain/munki-manager/AutoPkg/Cache/local.munki.BetterTouchTool/downloads/btt.zip",
        workspace="/Users/runner/work/munki-manager/munki-manager",
    )
    assert (
        out
        == "/Users/runner/work/munki-manager/munki-manager/AutoPkg/Cache/local.munki.BetterTouchTool/downloads/btt.zip"
    )


def test_rewrites_legacy_github_runner_path_to_mac_mini():
    out = mod._rewrite_file_path(
        "/Users/runner/work/munki-manager/munki-manager/AutoPkg/Cache/local.munki.Arc/downloads/Arc.zip",
        workspace="/opt/UnitySrc/joncrain/munki-manager",
    )
    assert (
        out
        == "/opt/UnitySrc/joncrain/munki-manager/AutoPkg/Cache/local.munki.Arc/downloads/Arc.zip"
    )


def test_leaves_unrelated_absolute_paths_alone():
    # Without the /AutoPkg/Cache/ anchor we have no idea where the previous
    # workspace ends; rewriting blindly would corrupt the path.
    out = mod._rewrite_file_path(
        "/var/tmp/something.zip", workspace="/Users/runner/work/foo/foo"
    )
    assert out == "/var/tmp/something.zip"


def test_handles_trailing_slash_on_workspace():
    out = mod._rewrite_file_path(
        "${WORKSPACE}/AutoPkg/Cache/x/downloads/x.dmg",
        workspace="/some/path/",
    )
    assert out == "/some/path/AutoPkg/Cache/x/downloads/x.dmg"


def test_walks_full_cache_structure_only_touching_file_path():
    cache = {
        "Firefox.munki.recipe": {
            "metadata": [
                {
                    "etag": '"e1"',
                    "file_path": "/opt/UnitySrc/joncrain/munki-manager/AutoPkg/Cache/local.munki.Firefox/downloads/firefox.dmg",
                    "file_size": 100,
                }
            ],
            "timestamp": "2026-05-25 03:18:12+00:00",
        }
    }
    out = mod._rewrite_paths(cache, "/Users/runner/work/munki-manager/munki-manager")
    md = out["Firefox.munki.recipe"]["metadata"][0]
    assert (
        md["file_path"]
        == "/Users/runner/work/munki-manager/munki-manager/AutoPkg/Cache/local.munki.Firefox/downloads/firefox.dmg"
    )
    assert md["etag"] == '"e1"'
    assert md["file_size"] == 100
    assert out["Firefox.munki.recipe"]["timestamp"] == "2026-05-25 03:18:12+00:00"
