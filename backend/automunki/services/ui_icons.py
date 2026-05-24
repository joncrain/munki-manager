"""Software icons (PNG) stored in the database.

Icons are served to both Munki clients (``/repo/icons/<name>.png``) and the
web UI (``/api/v1/icons/<name>.png``, fronted by Next.js at ``/icons/…``).
The ``software_icon`` table is the single source of truth.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from automunki.models.software_icon import SoftwareIcon

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_MAX_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True)
class IconBlob:
    """In-memory icon, ready for an HTTP response."""

    name: str
    data: bytes
    content_type: str
    sha256: str
    size_bytes: int


def sanitize_icon_basename(name: str) -> str:
    """Munki ``icon_name``: filename stem, safe for disk and URLs."""
    s = name.strip()
    s = re.sub(r"\.png$", "", s, flags=re.IGNORECASE)
    s = re.sub(r"[^\w.\-]+", "_", s, flags=re.UNICODE)
    s = s.strip("._-")
    if not s or len(s) > 120:
        raise ValueError("Invalid icon name")
    if ".." in s or "/" in s or "\\" in s:
        raise ValueError("Invalid icon name")
    return s


def validate_png(data: bytes) -> None:
    if len(data) > _MAX_BYTES:
        raise ValueError("File too large (max 2MB)")
    if len(data) < 8 or not data.startswith(_PNG_MAGIC):
        raise ValueError("Only PNG images are supported")


async def store_icon(session: AsyncSession, stem: str, data: bytes) -> tuple[str, str]:
    """Upsert ``{stem}.png`` into the DB. Returns ``(icon_name, filename)``."""
    validate_png(data)
    safe = sanitize_icon_basename(stem)
    digest = hashlib.sha256(data).hexdigest()

    row = (await session.execute(select(SoftwareIcon).where(SoftwareIcon.name == safe))).scalar_one_or_none()
    if row is None:
        row = SoftwareIcon(
            name=safe,
            data=data,
            content_type="image/png",
            sha256=digest,
            size_bytes=len(data),
        )
        session.add(row)
    else:
        row.data = data
        row.content_type = "image/png"
        row.sha256 = digest
        row.size_bytes = len(data)

    await session.commit()
    return safe, f"{safe}.png"


async def get_icon_by_name(session: AsyncSession, stem: str) -> IconBlob | None:
    """Fetch an icon by stem. Returns ``None`` when not found."""
    try:
        safe = sanitize_icon_basename(stem)
    except ValueError:
        return None
    row = (await session.execute(select(SoftwareIcon).where(SoftwareIcon.name == safe))).scalar_one_or_none()
    if row is None:
        return None
    return IconBlob(
        name=row.name,
        data=row.data,
        content_type=row.content_type or "image/png",
        sha256=row.sha256,
        size_bytes=row.size_bytes,
    )


async def list_icon_hashes(session: AsyncSession) -> dict[str, str]:
    """Return ``{"<name>.png": "<sha256-hex>"}`` for every stored icon.

    Munki writes this into ``_icon_hashes.plist`` and uses it to skip
    re-downloading icons that haven't changed.
    """
    rows = (await session.execute(select(SoftwareIcon.name, SoftwareIcon.sha256))).all()
    return {f"{name}.png": digest for name, digest in rows}
