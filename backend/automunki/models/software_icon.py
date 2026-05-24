"""Software icons (PNG) served to Munki clients and the web UI.

Keyed by ``name`` — the Munki ``icon_name`` value from pkginfo (filename stem,
no ``.png`` suffix). Munki clients hit ``/repo/icons/<name>.png``; the web UI
hits ``/icons/<name>.png`` which Next.js rewrites to ``/api/v1/icons/<name>.png``.
Both endpoints read from this single table.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, LargeBinary, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from automunki.models.base import Base, UUIDMixin


class SoftwareIcon(UUIDMixin, Base):
    __tablename__ = "software_icon"

    #: Filename stem (Munki ``icon_name``), sanitised. Unique.
    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)

    #: PNG bytes. Stored in Postgres ``bytea``. Icons are small (few KB each)
    #: so BYTEA is the right call over LargeObject.
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    #: Always ``image/png`` today; kept explicit for future formats.
    content_type: Mapped[str] = mapped_column(Text, nullable=False, default="image/png")

    #: SHA-256 hex digest of ``data``. Used for ETag + ``_icon_hashes.plist``.
    sha256: Mapped[str] = mapped_column(Text, nullable=False, index=True)

    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
