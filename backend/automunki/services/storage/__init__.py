"""Storage backend factory.

``get_storage_backend()`` returns a process-wide singleton chosen from
``settings.storage_backend``. The singleton pattern matters because the Azure
and S3 SDK clients are pooled internally; rebuilding them per request would
defeat connection reuse.
"""

from __future__ import annotations

import threading

from automunki.core.config import settings
from automunki.services.storage.base import (
    StorageBackend,
    StorageNotConfiguredError,
    sanitize_relative_path,
)
from automunki.services.storage.noop import NoopStorageBackend

__all__ = [
    "StorageBackend",
    "StorageNotConfiguredError",
    "get_storage_backend",
    "reset_storage_backend",
    "sanitize_relative_path",
]


_LOCK = threading.Lock()
_INSTANCE: StorageBackend | None = None


def get_storage_backend() -> StorageBackend:
    """Return the currently configured backend, initializing it on first use."""
    global _INSTANCE
    if _INSTANCE is not None:
        return _INSTANCE
    with _LOCK:
        if _INSTANCE is not None:
            return _INSTANCE
        _INSTANCE = _build_backend()
        return _INSTANCE


def reset_storage_backend() -> None:
    """Clear the cached singleton (used by tests that flip ``storage_backend``)."""
    global _INSTANCE
    with _LOCK:
        _INSTANCE = None


def _build_backend() -> StorageBackend:
    name = (settings.storage_backend or "none").lower()
    if name == "none":
        return NoopStorageBackend()
    if name == "azure_blob":
        from automunki.services.storage.azure_blob import AzureBlobStorageBackend

        return AzureBlobStorageBackend()
    if name == "s3":
        from automunki.services.storage.s3 import S3StorageBackend

        return S3StorageBackend()
    raise StorageNotConfiguredError(f"Unknown STORAGE_BACKEND={name!r}")
