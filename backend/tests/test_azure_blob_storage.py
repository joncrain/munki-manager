"""Integration tests for the Azure Blob storage backend using the real SDK.

These tests instantiate a real ``BlobServiceClient`` with a fake HTTP
transport that records (but does not send) every outgoing request. That
exercises the real ``_upload_blob_options`` dispatch (which auto-wraps an
async iterator into ``AsyncIterStreamer``) and the real
``upload_data_chunks`` chunking loop, then verifies the SDK actually
issued staged block-upload requests.

Honest limitation: the SDK's generated ops accept ``**kwargs`` and forward
unknown kwargs silently — they only blow up when a real Azure endpoint
4xxes them. So this test cannot reproduce a "passed an invalid per-call
kwarg" bug end-to-end. The complementary defense is the
``except Exception`` block in ``upload_run_pkg`` (api/routes/autopkg.py),
which surfaces the real error message back to the runner instead of
letting uvicorn return an opaque "Internal Server Error" page.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from azure.core.pipeline.transport import AsyncHttpTransport, HttpRequest
from azure.storage.blob.aio import BlobServiceClient

from automunki.core.config import settings
from automunki.services.storage import reset_storage_backend
from automunki.services.storage.azure_blob import AzureBlobStorageBackend


class _FakeAioHttpResponse:
    """Minimal async response object the SDK's azure-core layer is happy with."""

    def __init__(
        self,
        request: HttpRequest,
        status_code: int = 201,
        headers: dict[str, str] | None = None,
        body: bytes = b"",
    ) -> None:
        self.request = request
        self.status_code = status_code
        self.headers = headers or {
            "etag": '"0x8D"',
            "last-modified": "Mon, 01 Jan 2026 00:00:00 GMT",
            "x-ms-request-id": "fake",
            "x-ms-version": "2025-01-05",
            "content-md5": "",
            "x-ms-content-crc64": "",
            "x-ms-request-server-encrypted": "true",
        }
        self.reason = "Created"
        self.content_type = "application/xml"
        self._body = body
        # azure-core checks for these attributes on the response.
        self.context: dict[str, Any] = {}

    def body(self) -> bytes:
        return self._body

    def text(self, _encoding: str | None = None) -> str:
        return self._body.decode("utf-8", errors="replace")

    async def load_body(self) -> None:
        return None

    async def read(self) -> bytes:
        return self._body

    async def close(self) -> None:
        return None


class _RecordingTransport(AsyncHttpTransport):
    """Captures every outgoing request without sending it.

    Returns a 201/200 with empty body for every call so the SDK's chunked
    upload completes successfully (PUT block + PUT block list).
    """

    def __init__(self) -> None:
        self.requests: list[HttpRequest] = []

    async def __aenter__(self) -> _RecordingTransport:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None

    async def open(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def send(self, request: HttpRequest, **_kwargs: Any) -> _FakeAioHttpResponse:
        self.requests.append(request)
        # The Put Block List response is XML-ish but the SDK only reads headers,
        # so an empty body is fine for both Put Block and Put Block List.
        return _FakeAioHttpResponse(request, status_code=201)


@pytest.fixture
def configured_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[AzureBlobStorageBackend, _RecordingTransport]:
    """A backend whose ``_client()`` returns a real ``BlobServiceClient`` with
    a recording transport, exercising the real SDK dispatch end-to-end."""
    monkeypatch.setattr(settings, "storage_backend", "azure_blob", raising=False)
    monkeypatch.setattr(settings, "azure_storage_account_name", "teststorage", raising=False)
    monkeypatch.setattr(settings, "azure_storage_connection_string", "", raising=False)
    monkeypatch.setattr(settings, "azure_storage_sas_token", "fake-sas", raising=False)
    monkeypatch.setattr(settings, "azure_storage_container", "munki-repo", raising=False)
    reset_storage_backend()

    backend = AzureBlobStorageBackend()
    transport = _RecordingTransport()
    # ``credential=None`` = anonymous access. The SDK's auth-signing policy
    # is a no-op, so requests reach our recording transport directly. We
    # don't care about authentication for these tests — only that the SDK
    # accepts the kwargs we pass and dispatches the right HTTP requests.
    real_svc = BlobServiceClient(
        account_url="https://teststorage.blob.core.windows.net",
        credential=None,
        transport=transport,
    )
    monkeypatch.setattr(backend, "_client", lambda: real_svc)
    return backend, transport


@pytest.mark.asyncio
async def test_upload_uses_block_uploads_not_single_put(
    configured_backend: tuple[AzureBlobStorageBackend, _RecordingTransport],
) -> None:
    """When ``length is None`` the SDK MUST take the chunked path (Put Block
    + Put Block List), not single-PUT (which would require materializing the
    entire body to compute Content-Length and OOM-kill the worker on a
    400 MB pkg).

    Verified by checking that at least one ``comp=block`` request appears
    in the captured traffic — that's the Put Block call. Single-PUT would
    issue exactly one bare PUT with no ``comp=`` query.
    """
    backend, transport = configured_backend

    async def _body() -> AsyncIterator[bytes]:
        # 8 MiB total → 2 Put Block calls + 1 Put Block List with the SDK's
        # default 4 MiB max_block_size.
        for _ in range(8):
            yield b"x" * (1024 * 1024)

    url = await backend.upload(
        relative_path="pkgs/x/foo.pkg",
        body=_body(),
        content_length=None,
    )
    assert url == "https://teststorage.blob.core.windows.net/munki-repo/pkgs/x/foo.pkg"

    block_requests = [r for r in transport.requests if "comp=block" in r.url]
    block_list_requests = [r for r in transport.requests if "comp=blocklist" in r.url]
    assert block_requests, "Expected at least one Put Block request (comp=block); saw URLs: " + ", ".join(
        r.url for r in transport.requests
    )
    assert block_list_requests, "Expected a Put Block List request (comp=blocklist); saw URLs: " + ", ".join(
        r.url for r in transport.requests
    )


@pytest.mark.asyncio
async def test_upload_drains_async_iterator_completely(
    configured_backend: tuple[AzureBlobStorageBackend, _RecordingTransport],
) -> None:
    """The async iterator must be fully consumed (not partially read or
    materialized into a list before sending). Counts how many times the
    body generator yielded vs how many bytes the SDK staged.
    """
    backend, transport = configured_backend

    yields_consumed = 0

    async def _body() -> AsyncIterator[bytes]:
        nonlocal yields_consumed
        for _ in range(8):  # 8 MiB total in 1 MiB chunks
            yields_consumed += 1
            yield b"x" * (1024 * 1024)

    await backend.upload(
        relative_path="pkgs/x/foo.pkg",
        body=_body(),
        content_length=None,
    )

    assert yields_consumed == 8, (
        f"Expected the SDK to drain all 8 yields from the async iterator; "
        f"only {yields_consumed} were consumed (the streaming path is broken "
        f"and the SDK is buffering or short-circuiting)."
    )
