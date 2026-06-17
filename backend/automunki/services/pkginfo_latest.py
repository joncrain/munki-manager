"""Latest-version helpers for pkginfo rows (Munki loose version ordering)."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from sqlalchemy import select

from automunki.models.munki import PkgInfo
from automunki.services.loose_version import compare_loose_versions

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def compute_latest_version_by_name(rows: Iterable[tuple[str, str]]) -> dict[str, str]:
    """Return the highest loose version string per pkginfo ``name``."""
    latest: dict[str, str] = {}
    for name, version in rows:
        if name not in latest or compare_loose_versions(version, latest[name]) > 0:
            latest[name] = version
    return latest


async def fetch_latest_version_by_name(
    session: AsyncSession,
    names: set[str] | None = None,
) -> dict[str, str]:
    """Load latest version per non-deleted pkginfo name from the database."""
    query = select(PkgInfo.name, PkgInfo.version).where(PkgInfo.is_deleted.is_(False))
    if names:
        query = query.where(PkgInfo.name.in_(names))
    result = await session.execute(query)
    return compute_latest_version_by_name(result.all())


def is_latest_version(name: str, version: str, latest_by_name: dict[str, str]) -> bool:
    return latest_by_name.get(name) == version
