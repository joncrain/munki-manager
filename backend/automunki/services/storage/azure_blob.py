"""Azure Blob Storage backend.

Auth precedence (matching the comments in ``backend/automunki/core/config.py``):

1. ``azure_storage_connection_string`` — full account+key string.
2. ``azure_storage_account_name`` + ``azure_storage_sas_token`` — SAS-only.
3. ``azure_storage_account_name`` alone — fall back to ``DefaultAzureCredential``
   (managed identity in Container Apps / az CLI / env vars locally).

The ``azure-storage-blob`` and ``azure-identity`` packages are imported lazily
so deployments that stay on ``STORAGE_BACKEND=none`` don't need the optional
``[azure]`` extra installed.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import ClassVar

import structlog

from automunki.core.config import settings
from automunki.services.storage.base import (
    StorageNotConfiguredError,
    sanitize_relative_path,
)

logger = structlog.get_logger()


class AzureBlobStorageBackend:
    name: ClassVar[str] = "azure_blob"

    def __init__(self) -> None:
        # Lazy import: the [azure] extra is optional.
        try:
            from azure.storage.blob.aio import BlobServiceClient  # type: ignore[import-untyped]
        except ImportError as e:
            raise StorageNotConfiguredError(
                'azure-storage-blob is not installed; run `pip install -e ".[azure]"`'
            ) from e

        self._BlobServiceClient = BlobServiceClient
        self._container = settings.azure_storage_container or "munki-repo"
        self._account = settings.azure_storage_account_name.strip()
        self._conn_str = settings.azure_storage_connection_string.strip()
        self._sas_token = settings.azure_storage_sas_token.strip()

        if not self._conn_str and not self._account:
            raise StorageNotConfiguredError(
                "Azure storage requires AZURE_STORAGE_CONNECTION_STRING or AZURE_STORAGE_ACCOUNT_NAME"
            )

    def _client(self):
        if self._conn_str:
            return self._BlobServiceClient.from_connection_string(self._conn_str)
        account_url = f"https://{self._account}.blob.core.windows.net"
        if self._sas_token:
            credential: object = self._sas_token
        else:
            try:
                from azure.identity.aio import DefaultAzureCredential  # type: ignore[import-untyped]
            except ImportError as e:
                raise StorageNotConfiguredError(
                    'azure-identity is not installed; run `pip install -e ".[azure]"`'
                ) from e
            credential = DefaultAzureCredential()
        return self._BlobServiceClient(account_url=account_url, credential=credential)

    def _public_url(self, relative_path: str) -> str:
        if self._account:
            account = self._account
        else:
            # Parse account name from connection string for URL construction.
            # ``DefaultEndpointsProtocol=https;AccountName=foo;AccountKey=...``
            account = ""
            for part in self._conn_str.split(";"):
                if part.startswith("AccountName="):
                    account = part[len("AccountName=") :]
                    break
            if not account:
                raise StorageNotConfiguredError("Could not determine Azure storage account name for URL")
        return f"https://{account}.blob.core.windows.net/{self._container}/{relative_path}"

    async def upload(
        self,
        *,
        relative_path: str,
        body: AsyncIterator[bytes],
        content_length: int | None,
        content_type: str = "application/octet-stream",
    ) -> str:
        from azure.storage.blob import ContentSettings  # type: ignore[import-untyped]

        rel = sanitize_relative_path(relative_path)
        async with self._client() as svc:
            container = svc.get_container_client(self._container)
            try:
                await container.create_container()
            except Exception:
                pass
            blob = container.get_blob_client(rel)

            # Pass the async iterator straight through. The SDK auto-wraps it
            # in ``AsyncIterStreamer`` (a file-like adapter with ``read(size)``)
            # and — because the wrapped stream is non-seekable AND we pass
            # ``length=None`` — routes to staged-block uploads via
            # ``upload_data_chunks``. Peak memory stays bounded at roughly
            # ``max_block_size * max_concurrency`` (4 MiB × 4 ≈ 16 MiB)
            # regardless of total upload size, which is what we need on a
            # 1 GiB backend container handling multi-hundred-MB pkgs.
            #
            # GOTCHA: ``max_single_put_size`` is a *client-init* kwarg
            # (``BlobServiceClient(..., max_single_put_size=...)``), NOT a
            # per-call kwarg on ``upload_blob``. Passing it here used to
            # cause a 500 because it leaked into the underlying
            # ``stage_block`` REST call as an unknown query/header parameter.
            # The single-PUT branch is already skipped automatically when
            # ``length is None``, so we don't need to override the threshold.
            await blob.upload_blob(
                body,
                overwrite=True,
                length=content_length,
                max_concurrency=4,
                content_settings=ContentSettings(content_type=content_type),
            )
        return self._public_url(rel)

    async def invalidate_cdn(self, paths: list[str]) -> None:
        profile = settings.azure_cdn_profile.strip()
        endpoint = settings.azure_cdn_endpoint.strip()
        if not profile or not endpoint or not paths:
            return
        try:
            # ``azure-mgmt-cdn`` is heavier than the storage SDK and is only
            # needed when an operator wires up a CDN/Front Door endpoint.
            from azure.identity.aio import DefaultAzureCredential  # type: ignore[import-untyped]
            from azure.mgmt.cdn.aio import CdnManagementClient  # type: ignore[import-untyped]
        except ImportError:
            logger.warning(
                "azure_cdn_invalidation_skipped",
                reason="azure-mgmt-cdn not installed",
            )
            return
        try:
            sub_id = settings.azure_subscription_id if hasattr(settings, "azure_subscription_id") else ""
        except Exception:
            sub_id = ""
        if not sub_id:
            logger.warning("azure_cdn_invalidation_skipped", reason="no subscription_id")
            return
        try:
            cred = DefaultAzureCredential()
            async with CdnManagementClient(cred, sub_id) as client:
                await client.endpoints.begin_purge_content(
                    resource_group_name=profile.split("/")[0],
                    profile_name=profile.split("/")[-1],
                    endpoint_name=endpoint,
                    content_file_paths={"content_paths": [f"/{p}" for p in paths]},
                )
        except Exception as e:
            logger.warning("azure_cdn_invalidation_failed", error=str(e))
