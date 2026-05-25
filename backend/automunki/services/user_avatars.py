"""User profile avatars stored as bytes in Postgres.

Why in the database, not on disk:

- Azure Container Apps containers have ephemeral overlay filesystems.
  Anything written outside a mounted volume is lost on revision restart.
- ACA also runs multiple replicas behind a load balancer; an avatar
  written to replica A's local disk is invisible to replica B.

We considered Azure Blob Storage but the per-user payload is bounded at
~1 MB (see :data:`MAX_AVATAR_BYTES`), there's at most one avatar per
user, and ``user`` is a small table for any realistic deployment of this
app. Storing the raw bytes inline keeps Terraform simple and avoids a
SAS-URL surface for what is effectively a low-value asset.

The :class:`User.avatar_data` column is ``deferred`` at the ORM level so
the bytes don't load on every authenticated request — only the
explicit avatar GET handler undefers and reads them.
"""

from __future__ import annotations

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_JPEG_MAGIC = b"\xff\xd8\xff"
MAX_AVATAR_BYTES = 1024 * 1024  # 1 MB. Bounded so a single bytea fits in a TOAST page block.


def detect_image(data: bytes) -> str:
    """Return the media type for *data* (PNG or JPEG only).

    Validates by **content magic**, not the upload's claimed Content-Type or
    filename suffix — a client that sends a PDF named ``avatar.png`` should
    still be rejected. Raises :class:`ValueError` with a user-facing message
    on any rejection so the route can surface 422 with the same text.
    """
    if len(data) > MAX_AVATAR_BYTES:
        raise ValueError(f"Image too large (max {MAX_AVATAR_BYTES // 1024} KB)")
    if len(data) < 8:
        raise ValueError("Invalid image file")
    if data.startswith(_PNG_MAGIC):
        return "image/png"
    if data.startswith(_JPEG_MAGIC):
        return "image/jpeg"
    raise ValueError("Only PNG or JPEG images are supported")
