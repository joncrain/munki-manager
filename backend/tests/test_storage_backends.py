"""Storage backend factory + path sanitization + noop semantics."""

from __future__ import annotations

import pytest

from automunki.core.config import settings
from automunki.services import storage
from automunki.services.storage import (
    StorageNotConfiguredError,
    get_storage_backend,
    reset_storage_backend,
    sanitize_relative_path,
)
from automunki.services.storage.noop import NoopStorageBackend


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("pkgs/Firefox.pkg", "pkgs/Firefox.pkg"),
        ("/leading/slash/foo.pkg", "leading/slash/foo.pkg"),
        ("a/b/c.pkg", "a/b/c.pkg"),
    ],
)
def test_sanitize_relative_path_accepts_normal_paths(raw: str, expected: str) -> None:
    assert sanitize_relative_path(raw) == expected


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "../escape",
        "pkgs/../etc/passwd",
        "pkgs//double",
        "pkgs/./trick",
        "with\x00null/foo",
    ],
)
def test_sanitize_relative_path_rejects_pathological(bad: str) -> None:
    with pytest.raises(ValueError):
        sanitize_relative_path(bad)


def test_get_storage_backend_defaults_to_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "storage_backend", "none", raising=False)
    reset_storage_backend()
    backend = get_storage_backend()
    assert isinstance(backend, NoopStorageBackend)
    assert backend.name == "none"


def test_get_storage_backend_unknown_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "storage_backend", "magnetic-tape", raising=False)
    reset_storage_backend()
    with pytest.raises(StorageNotConfiguredError):
        get_storage_backend()


@pytest.mark.asyncio
async def test_noop_upload_raises_and_drains_body(monkeypatch: pytest.MonkeyPatch) -> None:
    """The 503 path must still consume the body so callers don't hang on send."""
    monkeypatch.setattr(settings, "storage_backend", "none", raising=False)
    reset_storage_backend()
    backend = get_storage_backend()

    consumed: list[bytes] = []

    async def _gen():
        for chunk in (b"hello", b"world"):
            consumed.append(chunk)
            yield chunk

    with pytest.raises(StorageNotConfiguredError):
        await backend.upload(
            relative_path="pkgs/x/foo.pkg",
            body=_gen(),
            content_length=10,
            content_type="application/octet-stream",
        )
    # Body iterator was driven to completion before the exception bubbled.
    assert consumed == [b"hello", b"world"]


@pytest.mark.asyncio
async def test_noop_invalidate_cdn_is_no_op(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "storage_backend", "none", raising=False)
    reset_storage_backend()
    backend = get_storage_backend()
    # Should not raise even when called with paths.
    await backend.invalidate_cdn(["pkgs/x/foo.pkg"])
    # And the function returns None.
    assert await backend.invalidate_cdn([]) is None


def test_get_storage_backend_singleton(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "storage_backend", "none", raising=False)
    reset_storage_backend()
    a = get_storage_backend()
    b = get_storage_backend()
    assert a is b


def test_reset_storage_backend_clears_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "storage_backend", "none", raising=False)
    reset_storage_backend()
    a = get_storage_backend()
    reset_storage_backend()
    b = get_storage_backend()
    assert a is not b


def test_storage_module_exports() -> None:
    assert "get_storage_backend" in dir(storage)
    assert "StorageNotConfiguredError" in dir(storage)
    assert "sanitize_relative_path" in dir(storage)
