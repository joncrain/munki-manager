"""Resolve external Munki URLs (``PackageURL`` / ``ClientResourceURL``).

There are two configuration sources:

1. **Env vars** (``MUNKI_REPO_PKG_BASE_URL`` /
   ``MUNKI_REPO_CLIENT_RESOURCES_BASE_URL``). When set, these win; the DB
   row becomes read-only for that field. Matches the ``MunkiRepoBasicAuth``
   env-override pattern elsewhere in the app.
2. **DB singleton** (``munki_repo_urls``). Editable from the admin settings
   UI at runtime.

The "effective" URL for ``client_resource_url`` can *also* be auto-derived
from ``package_url`` when both are empty but the deployment clearly intends
them to live on the same host. Historically the redirect-based
implementation did this by swapping the last path segment of the pkg URL
with ``client_resources``. We preserve that behavior for continuity.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from automunki.core.config import settings
from automunki.models.munki_repo_urls import MunkiRepoUrls

SINGLETON_ID = 1


@dataclass(frozen=True)
class ResolvedRepoUrls:
    """Effective values used when building an enrollment profile."""

    #: Fully-qualified URL written into Munki's ``PackageURL`` pref. Empty
    #: means "omit the preference" (Munki falls back to
    #: ``<SoftwareRepoURL>/pkgs``, which for us no longer exists — so
    #: leaving this empty means a broken profile. The settings UI surfaces
    #: this).
    package_url: str
    #: Fully-qualified URL written into Munki's ``ClientResourceURL`` pref.
    #: Empty is fine — Munki then uses its default derivation
    #: ``<SoftwareRepoURL>/client_resources``, which we *do* serve statically.
    client_resource_url: str
    #: True when ``MUNKI_REPO_PKG_BASE_URL`` is set; the DB field is ignored.
    package_url_env_override: bool
    #: True when ``MUNKI_REPO_CLIENT_RESOURCES_BASE_URL`` is set; the DB
    #: field (and derivation) are ignored.
    client_resource_url_env_override: bool
    #: True when ``client_resource_url`` came from deriving a sibling of
    #: ``package_url`` rather than being set explicitly.
    client_resource_url_derived: bool


def _derive_client_resource_url(pkg_url: str) -> str:
    """Swap the last path segment of ``pkg_url`` with ``client_resources``.

    ``https://host/pkgs``         → ``https://host/client_resources``
    ``https://host/munki/pkgs``   → ``https://host/munki/client_resources``
    ``https://host``  (no path)   → ``""`` (can't safely invent a path)
    """
    pkg_url = (pkg_url or "").strip().rstrip("/")
    if not pkg_url:
        return ""
    parts = urlsplit(pkg_url)
    if not parts.path or parts.path == "/":
        return ""
    head, _, _last = parts.path.rpartition("/")
    new_path = f"{head}/client_resources" if head else "/client_resources"
    return urlunsplit((parts.scheme, parts.netloc, new_path, parts.query, parts.fragment))


async def get_singleton_row(session: AsyncSession) -> MunkiRepoUrls | None:
    r = await session.execute(select(MunkiRepoUrls).where(MunkiRepoUrls.id == SINGLETON_ID))
    return r.scalar_one_or_none()


async def _ensure_row(session: AsyncSession) -> MunkiRepoUrls:
    row = await get_singleton_row(session)
    if row is None:
        row = MunkiRepoUrls(id=SINGLETON_ID, package_url="", client_resource_url="")
        session.add(row)
        await session.flush()
    return row


def _env_pkg_url() -> str:
    return (settings.munki_repo_pkg_base_url or "").strip().rstrip("/")


def _env_client_resource_url() -> str:
    return (settings.munki_repo_client_resources_base_url or "").strip().rstrip("/")


async def resolve_repo_urls(session: AsyncSession) -> ResolvedRepoUrls:
    """Load the DB row, applying env overrides and derivation."""
    env_pkg = _env_pkg_url()
    env_cr = _env_client_resource_url()

    row = await get_singleton_row(session)
    db_pkg = (row.package_url if row else "").strip().rstrip("/")
    db_cr = (row.client_resource_url if row else "").strip().rstrip("/")

    pkg = env_pkg or db_pkg
    pkg_env = bool(env_pkg)

    if env_cr:
        cr = env_cr
        cr_env = True
        cr_derived = False
    elif db_cr:
        cr = db_cr
        cr_env = False
        cr_derived = False
    else:
        derived = _derive_client_resource_url(pkg)
        cr = derived
        cr_env = False
        cr_derived = bool(derived)

    return ResolvedRepoUrls(
        package_url=pkg,
        client_resource_url=cr,
        package_url_env_override=pkg_env,
        client_resource_url_env_override=cr_env,
        client_resource_url_derived=cr_derived,
    )


async def update_repo_urls(
    session: AsyncSession,
    *,
    package_url: str | None,
    client_resource_url: str | None,
) -> MunkiRepoUrls:
    """Upsert the singleton with user-supplied values.

    ``None`` means "leave this field alone"; empty string means "clear this
    field" (and fall back to derivation/env). Env-overridden fields cannot
    be written — the caller should block that at the route layer with a 409
    so the user gets a clear message.
    """
    row = await _ensure_row(session)
    if package_url is not None:
        row.package_url = (package_url or "").strip().rstrip("/")
    if client_resource_url is not None:
        row.client_resource_url = (client_resource_url or "").strip().rstrip("/")
    await session.commit()
    await session.refresh(row)
    return row
