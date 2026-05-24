"""AWS S3 + (optional) CloudFront backend.

Uses ``boto3`` (already a core dep) wrapped in ``run_in_executor`` to keep the
event loop free during the upload. ``aioboto3`` is a strict superset but it's a
new dependency; running the synchronous SDK on a thread is fine for the small
number of pkg uploads per day a typical Munki repo sees.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import ClassVar

import structlog

from automunki.core.config import settings
from automunki.services.storage.base import (
    StorageNotConfiguredError,
    sanitize_relative_path,
)

logger = structlog.get_logger()


class S3StorageBackend:
    name: ClassVar[str] = "s3"

    def __init__(self) -> None:
        bucket = settings.aws_s3_bucket.strip()
        if not bucket:
            raise StorageNotConfiguredError("AWS_S3_BUCKET is required for s3 backend")
        self._bucket = bucket
        self._region = settings.aws_region.strip() or "us-east-1"
        self._cf_dist = settings.cloudfront_distribution_id.strip()

    def _client(self):
        import boto3

        kwargs: dict = {"region_name": self._region}
        ak = settings.aws_access_key_id.strip()
        sk = settings.aws_secret_access_key.strip()
        if ak and sk:
            kwargs["aws_access_key_id"] = ak
            kwargs["aws_secret_access_key"] = sk
        return boto3.client("s3", **kwargs)

    def _public_url(self, relative_path: str) -> str:
        if self._cf_dist:
            return f"https://{self._cf_dist}.cloudfront.net/{relative_path}"
        return f"https://{self._bucket}.s3.{self._region}.amazonaws.com/{relative_path}"

    async def upload(
        self,
        *,
        relative_path: str,
        body: AsyncIterator[bytes],
        content_length: int | None,
        content_type: str = "application/octet-stream",
    ) -> str:
        rel = sanitize_relative_path(relative_path)
        chunks: list[bytes] = []
        async for chunk in body:
            if chunk:
                chunks.append(chunk)
        data = b"".join(chunks)

        def _put() -> None:
            self._client().put_object(
                Bucket=self._bucket,
                Key=rel,
                Body=data,
                ContentType=content_type,
            )

        await asyncio.get_running_loop().run_in_executor(None, _put)
        return self._public_url(rel)

    async def invalidate_cdn(self, paths: list[str]) -> None:
        if not self._cf_dist or not paths:
            return
        import time

        def _invalidate() -> None:
            import boto3

            client = boto3.client("cloudfront")
            client.create_invalidation(
                DistributionId=self._cf_dist,
                InvalidationBatch={
                    "Paths": {"Quantity": len(paths), "Items": [f"/{p}" for p in paths]},
                    "CallerReference": f"automunki-{int(time.time() * 1000)}",
                },
            )

        try:
            await asyncio.get_running_loop().run_in_executor(None, _invalidate)
        except Exception as e:
            logger.warning("cloudfront_invalidation_failed", error=str(e))
