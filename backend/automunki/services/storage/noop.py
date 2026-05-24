"""Default storage backend — refuses uploads.

Selected when ``settings.storage_backend == "none"`` (the default), which keeps
existing deployments on the old "manual sync" workflow until an operator opts
in to the cloud uploader.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import ClassVar

from automunki.services.storage.base import StorageNotConfiguredError


class NoopStorageBackend:
    name: ClassVar[str] = "none"

    async def upload(
        self,
        *,
        relative_path: str,
        body: AsyncIterator[bytes],
        content_length: int | None,
        content_type: str = "application/octet-stream",
    ) -> str:
        # Drain the body so the client doesn't time out on a half-read body
        # before the 503 reaches them.
        try:
            async for _ in body:
                pass
        except Exception:
            pass
        raise StorageNotConfiguredError("STORAGE_BACKEND=none — configure 'azure_blob' or 's3' to enable uploads")

    async def invalidate_cdn(self, paths: list[str]) -> None:
        return None
