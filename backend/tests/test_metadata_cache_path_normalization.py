"""Unit tests for ``services.autopkg_metadata_cache``.

The bug this protects against: a Mac mini runner saved cache entries whose
``file_path`` looked like ``/opt/UnitySrc/joncrain/munki-manager/AutoPkg/Cache/...``
and the next GitHub-hosted runner blew up with ``FileNotFoundError`` /
``PermissionError`` when ``cloud-autopkg-runner`` tried to ``stat`` that path.

These tests pin:

- Round-trip: any runner-rooted path goes in, comes out as the requesting
  runner's expanded path.
- Idempotence: feeding an already-normalised entry through ``normalize`` again
  doesn't re-rewrite it.
- Safety: ``file_path`` values without a ``/AutoPkg/Cache/`` anchor are left
  alone (we'd rather show an unusual path in the runner log than corrupt it).
- Selectivity: only ``file_path`` is touched; other fields like ``etag`` or
  ``timestamp`` round-trip unchanged.
"""

from __future__ import annotations

from automunki.services.autopkg_metadata_cache import (
    WORKSPACE_PLACEHOLDER,
    expand_cache_entry,
    normalize_cache_entry,
)


def _entry(file_path: str) -> dict:
    return {
        "metadata": [
            {
                "etag": '"abc"',
                "file_path": file_path,
                "file_size": 1234,
                "last_modified": "Tue, 12 May 2026 07:55:30 GMT",
            }
        ],
        "timestamp": "2026-05-25 03:18:12.052096+00:00",
    }


# ── normalize_cache_entry ────────────────────────────────────────────────────


def test_normalize_local_mac_workspace_collapses_to_placeholder():
    entry = _entry(
        "/opt/UnitySrc/joncrain/munki-manager/AutoPkg/Cache/local.munki.BetterTouchTool/downloads/BetterTouchTool.zip"
    )
    out = normalize_cache_entry(entry)
    assert (
        out["metadata"][0]["file_path"]
        == f"{WORKSPACE_PLACEHOLDER}/AutoPkg/Cache/local.munki.BetterTouchTool/downloads/BetterTouchTool.zip"
    )


def test_normalize_github_runner_workspace_collapses_to_same_placeholder():
    # The whole point of this normalisation is that mac mini and GHA workspaces
    # converge to the same canonical form.
    entry = _entry("/Users/runner/work/munki-manager/munki-manager/AutoPkg/Cache/local.munki.Arc/downloads/Arc.zip")
    out = normalize_cache_entry(entry)
    assert out["metadata"][0]["file_path"] == f"{WORKSPACE_PLACEHOLDER}/AutoPkg/Cache/local.munki.Arc/downloads/Arc.zip"


def test_normalize_is_idempotent():
    already = _entry(f"{WORKSPACE_PLACEHOLDER}/AutoPkg/Cache/local.munki.Foo/downloads/foo.zip")
    out = normalize_cache_entry(already)
    assert out["metadata"][0]["file_path"] == already["metadata"][0]["file_path"]


def test_normalize_preserves_unrelated_fields():
    entry = _entry("/Users/runner/work/munki-manager/munki-manager/AutoPkg/Cache/x/downloads/x.dmg")
    out = normalize_cache_entry(entry)
    md = out["metadata"][0]
    assert md["etag"] == '"abc"'
    assert md["file_size"] == 1234
    assert md["last_modified"] == "Tue, 12 May 2026 07:55:30 GMT"
    assert out["timestamp"] == entry["timestamp"]


def test_normalize_leaves_paths_without_cache_anchor_alone():
    # If someone manually pointed at a file outside CACHE_DIR, log it as-is.
    entry = _entry("/var/tmp/oddly-placed.zip")
    out = normalize_cache_entry(entry)
    assert out["metadata"][0]["file_path"] == "/var/tmp/oddly-placed.zip"


def test_normalize_handles_non_dict_entry_unchanged():
    assert normalize_cache_entry("not-a-dict") == "not-a-dict"  # type: ignore[arg-type]
    assert normalize_cache_entry(None) is None


def test_normalize_handles_metadata_items_without_file_path():
    entry = {"metadata": [{"etag": '"abc"'}], "timestamp": "x"}
    out = normalize_cache_entry(entry)
    assert out["metadata"] == [{"etag": '"abc"'}]


# ── expand_cache_entry ───────────────────────────────────────────────────────


def test_expand_to_github_runner_workspace():
    stored = _entry(f"{WORKSPACE_PLACEHOLDER}/AutoPkg/Cache/local.munki.Foo/downloads/foo.zip")
    out = expand_cache_entry(stored, workspace="/Users/runner/work/munki-manager/munki-manager")
    assert (
        out["metadata"][0]["file_path"]
        == "/Users/runner/work/munki-manager/munki-manager/AutoPkg/Cache/local.munki.Foo/downloads/foo.zip"
    )


def test_expand_to_mac_mini_workspace():
    stored = _entry(f"{WORKSPACE_PLACEHOLDER}/AutoPkg/Cache/local.munki.Foo/downloads/foo.zip")
    out = expand_cache_entry(stored, workspace="/opt/UnitySrc/joncrain/munki-manager")
    assert (
        out["metadata"][0]["file_path"]
        == "/opt/UnitySrc/joncrain/munki-manager/AutoPkg/Cache/local.munki.Foo/downloads/foo.zip"
    )


def test_expand_strips_trailing_slash_on_workspace():
    stored = _entry(f"{WORKSPACE_PLACEHOLDER}/AutoPkg/Cache/x/downloads/x.dmg")
    out = expand_cache_entry(stored, workspace="/some/path/")
    assert out["metadata"][0]["file_path"] == "/some/path/AutoPkg/Cache/x/downloads/x.dmg"


def test_expand_leaves_legacy_unnormalised_paths_alone():
    # Old data written before this code shipped will still have raw absolute
    # paths. The client-side rescue handles those — server should not corrupt
    # them by treating "<not-a-placeholder>" as if it were one.
    legacy = _entry("/opt/UnitySrc/joncrain/munki-manager/AutoPkg/Cache/x/downloads/x.dmg")
    out = expand_cache_entry(legacy, workspace="/Users/runner/work/foo/foo")
    assert out["metadata"][0]["file_path"] == legacy["metadata"][0]["file_path"]


def test_expand_with_empty_workspace_is_a_noop():
    stored = _entry(f"{WORKSPACE_PLACEHOLDER}/AutoPkg/Cache/x/downloads/x.dmg")
    assert expand_cache_entry(stored, workspace="") == stored


# ── round-trip ────────────────────────────────────────────────────────────────


def test_round_trip_mac_mini_to_github_actions():
    """Mac mini saves; GitHub Actions loads."""
    saved = _entry("/opt/UnitySrc/joncrain/munki-manager/AutoPkg/Cache/local.munki.Firefox/downloads/firefox.dmg")
    stored = normalize_cache_entry(saved)
    served = expand_cache_entry(stored, workspace="/Users/runner/work/munki-manager/munki-manager")
    assert (
        served["metadata"][0]["file_path"]
        == "/Users/runner/work/munki-manager/munki-manager/AutoPkg/Cache/local.munki.Firefox/downloads/firefox.dmg"
    )


def test_round_trip_github_actions_to_mac_mini():
    """GitHub Actions saves; Mac mini loads."""
    saved = _entry(
        "/Users/runner/work/munki-manager/munki-manager/AutoPkg/Cache/local.munki.Firefox/downloads/firefox.dmg"
    )
    stored = normalize_cache_entry(saved)
    served = expand_cache_entry(stored, workspace="/opt/UnitySrc/joncrain/munki-manager")
    assert (
        served["metadata"][0]["file_path"]
        == "/opt/UnitySrc/joncrain/munki-manager/AutoPkg/Cache/local.munki.Firefox/downloads/firefox.dmg"
    )
