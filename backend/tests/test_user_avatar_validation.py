"""Unit tests for ``services.user_avatars.detect_image``.

The bug history we're protecting against:

- Original on-disk avatars worked locally (single process, real filesystem)
  but silently lost data on Azure Container Apps because each replica had
  its own ephemeral overlay. Avatars now live in Postgres ``user.avatar_data``
  (``LargeBinary``) and the only validation gate is :func:`detect_image`.
- A user uploading a non-image (PDF/HTML/etc.) renamed ``foo.png`` previously
  succeeded because the old code trusted the filename. We now classify by
  file-content magic only and surface a 422-friendly ``ValueError`` message
  the route can pass straight through to the API consumer.
"""

from __future__ import annotations

import pytest

from automunki.services.user_avatars import (
    MAX_AVATAR_BYTES,
    detect_image,
)


def test_png_magic_returns_image_png():
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    assert detect_image(png) == "image/png"


def test_jpeg_magic_returns_image_jpeg():
    jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 100
    assert detect_image(jpeg) == "image/jpeg"


def test_rejects_pdf_pretending_to_be_png():
    # File-content magic, not the upload's claimed Content-Type or filename.
    # Old code that switched on filename suffix would have accepted this.
    pdf_bytes = b"%PDF-1.7" + b"\x00" * 200
    with pytest.raises(ValueError, match="PNG or JPEG"):
        detect_image(pdf_bytes)


def test_rejects_empty_payload():
    with pytest.raises(ValueError, match="Invalid image"):
        detect_image(b"")


def test_rejects_too_short_payload():
    # Anything shorter than the longer magic (PNG = 8 bytes) is invalid by
    # construction; we surface the same generic message rather than leaking
    # a "this looks _almost_ like a PNG" hint.
    with pytest.raises(ValueError, match="Invalid image"):
        detect_image(b"\x89PNG")


def test_rejects_oversized_payload():
    too_big = b"\x89PNG\r\n\x1a\n" + b"\x00" * (MAX_AVATAR_BYTES + 1)
    with pytest.raises(ValueError, match="too large"):
        detect_image(too_big)


def test_accepts_payload_at_size_limit():
    at_limit = b"\x89PNG\r\n\x1a\n" + b"\x00" * (MAX_AVATAR_BYTES - 8)
    assert detect_image(at_limit) == "image/png"
