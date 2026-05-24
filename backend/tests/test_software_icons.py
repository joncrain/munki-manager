"""Software icon sanitization, PNG validation, and ``_icon_hashes.plist`` shape."""

from __future__ import annotations

import hashlib
import plistlib

import pytest

from automunki.core.rbac_middleware import _is_public_path
from automunki.services import ui_icons
from automunki.services.munki import compile_icon_hashes_plist
from automunki.services.ui_icons import sanitize_icon_basename, validate_png

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _fake_png(payload: bytes = b"fake") -> bytes:
    return _PNG_MAGIC + payload


# ---------------------------------------------------------------------------
# sanitize_icon_basename
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("AdobeReader", "AdobeReader"),
        ("AdobeReader.png", "AdobeReader"),
        ("Adobe Reader", "Adobe_Reader"),
        ("Creative Cloud Installer", "Creative_Cloud_Installer"),
        ("  Firefox.PNG  ", "Firefox"),
        ("zoom.us", "zoom.us"),
    ],
)
def test_sanitize_happy_paths(raw: str, expected: str) -> None:
    assert sanitize_icon_basename(raw) == expected


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "   ",
        "." * 130,  # too long
        "...",  # all-stripped
        ".-_",  # all-stripped
    ],
)
def test_sanitize_rejects_bad(bad: str) -> None:
    with pytest.raises(ValueError):
        sanitize_icon_basename(bad)


@pytest.mark.parametrize(
    "hostile,expected",
    [
        ("../etc/passwd", "etc_passwd"),
        ("foo/bar", "foo_bar"),
        ("foo\\bar", "foo_bar"),
        ("a/b/c.png", "a_b_c"),
    ],
)
def test_sanitize_neutralises_path_traversal(hostile: str, expected: str) -> None:
    """Slashes / backslashes must be replaced with ``_`` so no directory escape is possible."""
    result = sanitize_icon_basename(hostile)
    assert "/" not in result
    assert "\\" not in result
    assert result == expected


# ---------------------------------------------------------------------------
# validate_png
# ---------------------------------------------------------------------------


def test_validate_png_accepts_valid_magic() -> None:
    validate_png(_fake_png(b"contents"))


def test_validate_png_rejects_non_png() -> None:
    with pytest.raises(ValueError, match="PNG"):
        validate_png(b"GIF89a not a png")


def test_validate_png_rejects_too_large() -> None:
    oversized = _fake_png(b"\x00" * (3 * 1024 * 1024))
    with pytest.raises(ValueError, match="too large"):
        validate_png(oversized)


def test_validate_png_rejects_empty() -> None:
    with pytest.raises(ValueError):
        validate_png(b"")


# ---------------------------------------------------------------------------
# compile_icon_hashes_plist
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_icon_hashes_plist_is_filename_keyed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Munki expects ``{"Firefox.png": "<hex>", ...}`` — filenames, not stems."""

    adobe_sha = hashlib.sha256(b"adobe-bytes").hexdigest()
    firefox_sha = hashlib.sha256(b"firefox-bytes").hexdigest()

    async def fake_list_icon_hashes(_session):
        return {"AdobeReader.png": adobe_sha, "Firefox.png": firefox_sha}

    monkeypatch.setattr(ui_icons, "list_icon_hashes", fake_list_icon_hashes)

    plist_bytes = await compile_icon_hashes_plist(session=None)  # type: ignore[arg-type]
    parsed = plistlib.loads(plist_bytes)

    assert parsed == {"AdobeReader.png": adobe_sha, "Firefox.png": firefox_sha}
    # Munki literally reads the keys expecting the ".png" suffix; defensive assert.
    assert all(k.endswith(".png") for k in parsed.keys())


@pytest.mark.asyncio
async def test_icon_hashes_plist_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_list_icon_hashes(_session):
        return {}

    monkeypatch.setattr(ui_icons, "list_icon_hashes", fake_list_icon_hashes)

    plist_bytes = await compile_icon_hashes_plist(session=None)  # type: ignore[arg-type]
    assert plistlib.loads(plist_bytes) == {}


# ---------------------------------------------------------------------------
# /repo/icons/... path → stem mapping (exercised via sanitize + the inline
# slicing used in the handler)
# ---------------------------------------------------------------------------


def test_api_v1_icons_get_is_public() -> None:
    """Browser ``<img>`` tags can't attach a bearer token, so GETs must be public.

    POST ``/api/v1/icons/upload`` must still require auth.
    """
    assert _is_public_path("/api/v1/icons/Firefox.png", "GET") is True
    assert _is_public_path("/api/v1/icons/a/b/c.png", "GET") is True
    assert _is_public_path("/api/v1/icons/upload", "POST") is False


def test_repo_icons_are_public() -> None:
    """Munki clients hit ``/repo/icons/...`` without credentials (or with HTTP Basic)."""
    assert _is_public_path("/repo/icons/Firefox.png", "GET") is True


def test_repo_icon_path_strips_png_and_slashes() -> None:
    # The handler does: ``icon_name.rsplit('/', 1)[-1].removesuffix('.png')``
    # then sanitize. Make sure both legit inputs and hostile ones normalise.
    for incoming, expected in [
        ("AdobeReader.png", "AdobeReader"),
        ("some/dir/Firefox.png", "Firefox"),
        ("Brave.PNG", "Brave"),  # Munki preserves case but validate lower too
    ]:
        stem = incoming.rsplit("/", 1)[-1].removesuffix(".png").removesuffix(".PNG")
        assert sanitize_icon_basename(stem) == expected
