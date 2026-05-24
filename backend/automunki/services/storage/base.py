"""Storage backend abstraction for AutoPkg / direct-upload pkg bytes.

When ``settings.storage_backend == "none"``, runners write to local disk and
operators ``aws s3 sync`` / ``az storage blob upload-batch`` manually. With
``s3`` or ``azure_blob`` selected, the streaming upload endpoint
(``POST /api/v1/autopkg/runs/{id}/pkgs`` and the direct-upload route) routes
bytes through one of the implementations in this package.

See ``docs/storage-backends.md`` for the operator-facing documentation.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import ClassVar, Protocol, runtime_checkable


class StorageNotConfiguredError(Exception):
    """Raised when the active backend is ``none`` (or misconfigured)."""


@runtime_checkable
class StorageBackend(Protocol):
    """Protocol every storage backend implements.

    Implementations stream the request body in chunks rather than buffering the
    whole pkg/dmg in memory: the endpoint hands us an ``AsyncIterator[bytes]``
    sourced from FastAPI's ``UploadFile`` and we forward those chunks straight
    to the SDK.
    """

    name: ClassVar[str]

    async def upload(
        self,
        *,
        relative_path: str,
        body: AsyncIterator[bytes],
        content_length: int | None,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Upload bytes to the configured store and return the public URL.

        ``relative_path`` is the path under the configured container/bucket
        (e.g. ``pkgs/<recipe_slug>/<filename>.pkg``). It must not start with a
        slash and must not contain ``..`` components.
        """

    async def invalidate_cdn(self, paths: list[str]) -> None:
        """Best-effort CDN invalidation for the given paths.

        Implementations log on failure rather than raising — invalidation is a
        nice-to-have, not a correctness requirement (clients re-fetch within
        ``ClientCache`` TTLs anyway).
        """


def sanitize_relative_path(path: str) -> str:
    """Reject paths that would escape the container or look pathological.

    We accept ``a/b/c.pkg`` style relative paths only; absolute paths and
    parent traversal (``..``) raise ``ValueError`` so a malicious or buggy
    runner can't write to ``/`` or ``../other-tenant/...``.
    """
    s = path.strip().lstrip("/")
    if not s:
        raise ValueError("relative_path is empty")
    if "\x00" in s:
        raise ValueError("relative_path contains NUL")
    parts = s.split("/")
    for part in parts:
        if part in ("", ".", ".."):
            raise ValueError(f"relative_path contains invalid segment {part!r}")
    return "/".join(parts)
