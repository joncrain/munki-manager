"""Cover the runner-side pkg upload helper in ``AutoPkg/scripts/report_results.py``.

The runner script lives outside the backend package (it ships into the AutoPkg
container/local Mac), so we import it by file path and patch ``urllib.request``.
"""

from __future__ import annotations

import importlib.util
import io
import sys
import urllib.error
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "AutoPkg" / "scripts" / "report_results.py"


@pytest.fixture(scope="module")
def report_results_module():
    spec = importlib.util.spec_from_file_location("report_results", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["report_results"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_pkg_upload_returns_none_when_pkg_missing(report_results_module, tmp_path: Path) -> None:
    """If ``pkg_repo_path`` doesn't exist on disk, no upload attempted."""
    fn = report_results_module._post_multipart_upload_pkg
    out = fn("https://example.test/api/v1/autopkg", "run-id", "local.munki.foo", str(tmp_path / "missing.pkg"))
    assert out is None


def test_pkg_upload_returns_url_on_success(report_results_module, tmp_path: Path) -> None:
    """Happy path: server returns 200 with ``imported_pkg_url``."""
    pkg_path = tmp_path / "Firefox.pkg"
    pkg_path.write_bytes(b"\x00\x01" * 4096)

    fake_response = io.BytesIO(b'{"imported_pkg_url": "https://blob.test/pkgs/x/Firefox.pkg"}')
    fake_response.status = 200  # type: ignore[attr-defined]

    class FakeCM:
        def __enter__(self):
            return fake_response

        def __exit__(self, *exc):
            return False

    with patch.object(report_results_module.urllib.request, "urlopen", return_value=FakeCM()):
        out = report_results_module._post_multipart_upload_pkg(
            "https://example.test/api/v1/autopkg",
            "run-id",
            "local.munki.firefox",
            str(pkg_path),
        )
    assert out == "https://blob.test/pkgs/x/Firefox.pkg"


def test_pkg_upload_503_returns_none(report_results_module, tmp_path: Path) -> None:
    """503 (storage_backend=none) must be treated as 'skip' so legacy deployments still work."""
    pkg_path = tmp_path / "Firefox.pkg"
    pkg_path.write_bytes(b"\x00")

    err = urllib.error.HTTPError(
        url="https://example.test",
        code=503,
        msg="Service Unavailable",
        hdrs=None,  # type: ignore[arg-type]
        fp=io.BytesIO(b'{"detail":"STORAGE_BACKEND=none"}'),
    )

    with patch.object(report_results_module.urllib.request, "urlopen", side_effect=err):
        out = report_results_module._post_multipart_upload_pkg(
            "https://example.test/api/v1/autopkg",
            "run-id",
            "local.munki.firefox",
            str(pkg_path),
        )
    assert out is None


def test_pkg_upload_other_http_error_returns_none(report_results_module, tmp_path: Path) -> None:
    """Non-503 errors are also non-fatal; we just log and move on."""
    pkg_path = tmp_path / "x.pkg"
    pkg_path.write_bytes(b"abc")

    err = urllib.error.HTTPError(
        url="https://example.test",
        code=500,
        msg="Server Error",
        hdrs=None,  # type: ignore[arg-type]
        fp=io.BytesIO(b'{"detail":"oops"}'),
    )

    with patch.object(report_results_module.urllib.request, "urlopen", side_effect=err):
        out = report_results_module._post_multipart_upload_pkg(
            "https://example.test/api/v1/autopkg",
            "run-id",
            "local.munki.firefox",
            str(pkg_path),
        )
    assert out is None


def test_pkg_upload_includes_relative_path_form_field(report_results_module, tmp_path: Path) -> None:
    """When ``relative_path`` is passed, it must appear in the multipart body
    so the backend writes to the Munki-style ``pkgs/<installer_item_location>``
    layout instead of the slug-based fallback."""
    pkg_path = tmp_path / "Blender-arm64-5.1.1.dmg"
    pkg_path.write_bytes(b"dmg-bytes")

    fake_response = io.BytesIO(b'{"imported_pkg_url": "https://blob.test/x.dmg"}')
    fake_response.status = 200  # type: ignore[attr-defined]

    class FakeCM:
        def __enter__(self):
            return fake_response

        def __exit__(self, *exc):
            return False

    captured: dict[str, bytes] = {}

    def _capture(req, *a, **kw):
        captured["body"] = req.data
        return FakeCM()

    with patch.object(report_results_module.urllib.request, "urlopen", side_effect=_capture):
        report_results_module._post_multipart_upload_pkg(
            "https://example.test/api/v1/autopkg",
            "run-id",
            "local.munki.Blender",
            str(pkg_path),
            relative_path="pkgs/apps/Blender/Blender-arm64-5.1.1.dmg",
        )

    body = captured["body"]
    assert b'name="relative_path"' in body
    assert b"pkgs/apps/Blender/Blender-arm64-5.1.1.dmg" in body
    # ``recipe_identifier`` is still sent so the server can fall back if
    # ``relative_path`` is rejected by ``sanitize_relative_path``.
    assert b'name="recipe_identifier"' in body
    assert b"local.munki.Blender" in body


def test_pkg_upload_omits_relative_path_when_empty(report_results_module, tmp_path: Path) -> None:
    """Default behavior (no ``relative_path``) does not add the form field
    — important for backward compatibility with backends that haven't been
    updated to accept it."""
    pkg_path = tmp_path / "Firefox.pkg"
    pkg_path.write_bytes(b"pkg-bytes")

    fake_response = io.BytesIO(b'{"imported_pkg_url": "https://blob.test/x.pkg"}')
    fake_response.status = 200  # type: ignore[attr-defined]

    class FakeCM:
        def __enter__(self):
            return fake_response

        def __exit__(self, *exc):
            return False

    captured: dict[str, bytes] = {}

    def _capture(req, *a, **kw):
        captured["body"] = req.data
        return FakeCM()

    with patch.object(report_results_module.urllib.request, "urlopen", side_effect=_capture):
        report_results_module._post_multipart_upload_pkg(
            "https://example.test/api/v1/autopkg",
            "run-id",
            "local.munki.firefox",
            str(pkg_path),
        )

    assert b'name="relative_path"' not in captured["body"]
