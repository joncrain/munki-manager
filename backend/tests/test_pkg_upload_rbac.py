"""RBAC + helper coverage for the runner pkg-upload path."""

from __future__ import annotations

import pytest

from automunki.api.routes.autopkg import (
    _safe_pkg_filename,
    _slug_recipe_identifier,
)
from automunki.core.rbac_middleware import (
    _is_public_path,
    _local_runner_authenticated_path,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("local.munki.Firefox", "local.munki.Firefox"),
        ("com.github.autopkg.recipes.Firefox.munki", "com.github.autopkg.recipes.Firefox.munki"),
        ("a/b/../c", "a_b_.._c"),
        ("  spaced name  ", "spaced_name"),
        ("", "unknown-recipe"),
        ("---", "unknown-recipe"),
    ],
)
def test_slug_recipe_identifier(raw: str, expected: str) -> None:
    assert _slug_recipe_identifier(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Firefox-130.0.pkg", "Firefox-130.0.pkg"),
        ("/path/with/dirs/Firefox.pkg", "Firefox.pkg"),
        ("..\\windows\\Firefox.pkg", "Firefox.pkg"),
        ("", "upload.pkg"),
        ("___", "upload.pkg"),
        (None, "upload.pkg"),  # type: ignore[arg-type]
    ],
)
def test_safe_pkg_filename(raw, expected: str) -> None:
    assert _safe_pkg_filename(raw) == expected


def test_pkgs_endpoint_authenticated_via_local_runner_token() -> None:
    """The runner Bearer token must let ``POST .../runs/{id}/pkgs`` through."""
    path = "/api/v1/autopkg/runs/00000000-0000-0000-0000-000000000000/pkgs"
    assert _local_runner_authenticated_path(path, "POST") is True


def test_pkgs_endpoint_get_not_local_runner() -> None:
    path = "/api/v1/autopkg/runs/00000000-0000-0000-0000-000000000000/pkgs"
    assert _local_runner_authenticated_path(path, "GET") is False


def test_pkgs_endpoint_is_not_publicly_open() -> None:
    """The pkg upload endpoint requires the bearer token."""
    path = "/api/v1/autopkg/runs/00000000-0000-0000-0000-000000000000/pkgs"
    assert _is_public_path(path, "POST") is False


def test_unrelated_paths_still_rejected_by_local_runner() -> None:
    assert _local_runner_authenticated_path("/api/v1/autopkg/runs", "GET") is False
    assert _local_runner_authenticated_path("/api/v1/users", "POST") is False


# --- Regression tests for security finding 1.2 -----------------------------
#
# These endpoints were on the public allowlist and are now Bearer-gated.
# If any of these flip back to "public", the security review's Critical
# finding regresses — keep these assertions strict.

_RUN_ID = "00000000-0000-0000-0000-000000000000"


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/autopkg/pkginfo/ingest",
        "/api/v1/autopkg/icons/ingest",
        f"/api/v1/autopkg/runs/{_RUN_ID}/results",
        f"/api/v1/autopkg/runs/{_RUN_ID}/complete",
        f"/api/v1/autopkg/runs/{_RUN_ID}/fail",
        f"/api/v1/autopkg/runs/{_RUN_ID}/github-context",
    ],
)
def test_runner_ingest_endpoints_are_no_longer_public(path: str) -> None:
    """Closing the unauthenticated AutoPkg ingest hole — must stay closed."""
    assert _is_public_path(path, "POST") is False
    # GETs were never public for these paths, but assert anyway.
    assert _is_public_path(path, "GET") is False


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/autopkg/pkginfo/ingest",
        "/api/v1/autopkg/icons/ingest",
        f"/api/v1/autopkg/runs/{_RUN_ID}/results",
        f"/api/v1/autopkg/runs/{_RUN_ID}/complete",
        f"/api/v1/autopkg/runs/{_RUN_ID}/fail",
        f"/api/v1/autopkg/runs/{_RUN_ID}/github-context",
    ],
)
def test_runner_ingest_endpoints_are_in_local_runner_allowlist(path: str) -> None:
    """The same paths must still be callable with the LOCAL_RUNNER_TOKEN bearer."""
    assert _local_runner_authenticated_path(path, "POST") is True
    # And only POST — no shape changes from the removed public allowlist.
    assert _local_runner_authenticated_path(path, "GET") is False


def test_runner_allowlist_does_not_match_unrelated_run_subpaths() -> None:
    """Don't accidentally widen to ``/runs/{id}/anything``."""
    base = f"/api/v1/autopkg/runs/{_RUN_ID}"
    assert _local_runner_authenticated_path(f"{base}/cancel", "POST") is False
    assert _local_runner_authenticated_path(f"{base}/results/extra", "POST") is False
    assert _local_runner_authenticated_path(f"{base}/completed", "POST") is False
