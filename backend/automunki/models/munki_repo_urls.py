"""Singleton row for external Munki URLs (``PackageURL`` / ``ClientResourceURL``).

When set, these URLs are written into the client ``.mobileconfig`` so Munki
fetches packages and client-resource zips **directly** from those hosts
instead of going through this server. That avoids cross-origin redirect
gotchas (Munki's gurl drops ``Authorization`` on cross-origin 302s) and keeps
large object traffic off the app tier entirely.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from automunki.models.base import Base


class MunkiRepoUrls(Base):
    """Single row (``id`` = 1) holding external Munki URLs.

    Both columns default to empty string. Empty = "not configured", which
    means the corresponding preference is omitted from the profile.
    """

    __tablename__ = "munki_repo_urls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    #: Maps to Munki's ``PackageURL`` preference.
    package_url: Mapped[str] = mapped_column(Text, default="", server_default="")
    #: Maps to Munki's ``ClientResourceURL`` preference. Empty means "use
    #: Munki's default derivation" (``<SoftwareRepoURL>/client_resources``).
    client_resource_url: Mapped[str] = mapped_column(Text, default="", server_default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
