"""Munki repo endpoints.

Serves catalogs, manifests, packages, and icons using the URL structure
that Munki clients expect, so ``SoftwareRepoURL`` can point directly at
``https://automunki.example.com/repo``.
"""

import hashlib
from datetime import UTC, datetime
from email.utils import format_datetime, parsedate_to_datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from automunki.api.deps import get_session
from automunki.core.config import settings
from automunki.services.munki import (
    compile_catalog_plist,
    compile_icon_hashes_plist,
    compile_manifest_plist,
    get_catalog_by_name,
    get_catalog_last_modified,
    get_manifest_by_name,
)
from automunki.services.ui_icons import get_icon_by_name

router = APIRouter(prefix="/repo", tags=["munki-repo"])


def _etag_for(data: bytes) -> str:
    return f'"{hashlib.md5(data).hexdigest()}"'


def _conditional_plist_response(
    request: Request,
    plist_bytes: bytes,
    last_modified: datetime | None,
) -> Response:
    """Return a plist Response that honours If-None-Match / If-Modified-Since."""
    etag = _etag_for(plist_bytes)

    if_none_match = request.headers.get("if-none-match")
    if if_none_match and if_none_match.strip() == etag:
        return Response(status_code=304, headers={"ETag": etag})

    if last_modified:
        if last_modified.tzinfo is None:
            last_modified = last_modified.replace(tzinfo=UTC)
        ims = request.headers.get("if-modified-since")
        if ims:
            try:
                ims_dt = parsedate_to_datetime(ims)
                if ims_dt.tzinfo is None:
                    ims_dt = ims_dt.replace(tzinfo=UTC)
                if last_modified <= ims_dt:
                    return Response(status_code=304, headers={"ETag": etag})
            except (ValueError, TypeError):
                pass

    headers: dict[str, str] = {"ETag": etag}
    if last_modified:
        headers["Last-Modified"] = format_datetime(last_modified, usegmt=True)

    return Response(
        content=plist_bytes,
        media_type="application/xml",
        headers=headers,
    )


@router.get("/catalogs/{catalog_name}")
async def repo_catalog(
    catalog_name: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Serve a compiled Munki catalog plist by catalog name."""
    catalog = await get_catalog_by_name(session, catalog_name)
    if not catalog:
        raise HTTPException(status_code=404, detail="Catalog not found")

    plist_bytes = await compile_catalog_plist(session, catalog.id)
    last_modified = await get_catalog_last_modified(session, catalog.id)

    return _conditional_plist_response(request, plist_bytes, last_modified)


@router.get("/manifests/{manifest_name:path}")
async def repo_manifest(
    manifest_name: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Serve a compiled Munki manifest plist by manifest name.

    Supports subdirectory-style names (e.g. ``labs/machine1``).
    """
    manifest = await get_manifest_by_name(session, manifest_name)
    if not manifest:
        raise HTTPException(status_code=404, detail="Manifest not found")

    plist_bytes = await compile_manifest_plist(session, manifest.id)
    if not plist_bytes:
        raise HTTPException(status_code=404, detail="Manifest not found")

    last_modified = manifest.updated_at
    return _conditional_plist_response(request, plist_bytes, last_modified)


# NOTE: /repo/pkgs/* and /repo/client_resources/* are intentionally *not*
# served here. Munki fetches those directly from whatever ``PackageURL`` /
# ``ClientResourceURL`` are set to in the client profile. Routing them
# through this app broke downloads whenever the pkg host lived on a
# different origin, because Munki's ``gurl`` strips ``Authorization``
# headers on cross-origin redirects. See
# ``services/munki_repo_urls.py`` for how those URLs are configured.


@router.get("/icons/_icon_hashes.plist")
async def repo_icon_hashes(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Serve the ``_icon_hashes.plist`` that Munki uses to decide which icons to download."""
    plist_bytes = await compile_icon_hashes_plist(session)
    return _conditional_plist_response(request, plist_bytes, last_modified=None)


@router.get("/icons/{icon_name:path}")
async def repo_icon(
    icon_name: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Serve a Munki icon.

    Lookup order:
      1. ``MUNKI_REPO_ICON_BASE_URL`` — if set, 302 to that CDN/bucket (legacy/escape hatch).
      2. ``software_icon`` table — PNGs uploaded through the UI or ingested from disk.
      3. 404.
    """
    base = settings.munki_repo_icon_base_url.rstrip("/")
    if base:
        return RedirectResponse(url=f"{base}/icons/{icon_name}", status_code=302)

    stem = icon_name.rsplit("/", 1)[-1].removesuffix(".png")
    blob = await get_icon_by_name(session, stem)
    if blob is None:
        raise HTTPException(status_code=404, detail="Icon not found")

    etag = f'"{blob.sha256}"'
    if (request.headers.get("if-none-match") or "").strip() == etag:
        return Response(status_code=304, headers={"ETag": etag, "Cache-Control": "public, max-age=300"})

    return Response(
        content=blob.data,
        media_type=blob.content_type,
        headers={"ETag": etag, "Cache-Control": "public, max-age=300"},
    )
