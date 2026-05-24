"""Direct software upload endpoint.

The ``/software`` page in the UI lets admins drop a ``.pkg`` or ``.dmg`` and
have the backend run a munkiimport-equivalent step on it: hash, basic xar
metadata extraction (.pkg only), upload to the configured storage backend,
then create a ``PkgInfo`` row. ``.dmg`` uploads — and any ``.pkg`` we couldn't
fully parse — are flagged ``pending_metadata=True`` so the UI can surface a
"finish me" badge and the admin completes the missing fields manually.

Because ``munkiimport`` is macOS-only, we do **not** shell out to it. See
``backend/automunki/services/munki_import.py`` for the Linux-side implementation.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from automunki.api.deps import get_session
from automunki.core.security import current_optional_user
from automunki.models.munki import Catalog, PkgInfo, PkgInfoCatalog
from automunki.models.user import User
from automunki.schemas.munki import PkgInfoRead
from automunki.services.audit import create_audit_entry
from automunki.services.munki_import import (
    build_import_plan,
    cleanup_temp,
    stream_upload_to_temp,
)
from automunki.services.storage import StorageNotConfiguredError, get_storage_backend

router = APIRouter(prefix="/munki", tags=["munki"])


def _catalog_names_form(value: str) -> list[str]:
    """Allow ``catalogs=a,b`` (comma-separated) or repeated form fields."""
    if not value:
        return []
    return [s.strip() for s in value.replace(";", ",").split(",") if s.strip()]


def _pkg_to_read(pkg: PkgInfo, catalog_names: list[str]) -> PkgInfoRead:
    base = PkgInfoRead.model_validate(pkg)
    return base.model_copy(update={"catalog_names": catalog_names})


@router.post("/upload", response_model=PkgInfoRead, status_code=201)
async def upload_software(
    file: UploadFile = File(...),
    display_name: str = Form(...),
    name: str = Form(""),
    catalogs: str = Form("testing"),
    category: str = Form(""),
    developer: str = Form(""),
    description: str = Form(""),
    unattended_install: bool = Form(False),
    munki_repo_subdir: str = Form(""),
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(current_optional_user),
) -> PkgInfoRead:
    """Accept a pkg/dmg, run munkiimport-lite, create a ``PkgInfo`` row.

    Returns ``PkgInfoRead`` with ``pending_metadata`` set when extraction
    couldn't infer a version/receipts (always for ``.dmg`` on Linux). The
    ``installer_item_location`` on the returned row is the path *relative to*
    ``pkgs/`` (e.g. ``apps/Slack/Slack-1.2.3.pkg`` when
    ``munki_repo_subdir=apps/Slack``, or just ``Slack-1.2.3.pkg`` at the
    root). Munki clients prepend ``MUNKI_REPO_PKG_BASE_URL`` to resolve the
    download URL. The blob in object storage is uploaded to the matching
    ``pkgs/<location>`` so the path the operator sees in the pkginfo
    mirrors the storage layout.

    ``munki_repo_subdir`` is optional; when empty the file lands at the root
    of ``pkgs/``. A leading ``pkgs/`` in the value is tolerated and stripped.

    503 is returned when ``STORAGE_BACKEND=none`` so the UI can prompt the
    operator to configure object storage before retrying.

    RBAC: gated by the ``munki.software`` page key with ``write`` access — the
    same permission required to edit pkginfo through the existing routes.
    """
    if not file.filename:
        raise HTTPException(status_code=422, detail="A filename is required")
    catalog_names = _catalog_names_form(catalogs) or ["testing"]

    storage = get_storage_backend()

    async def _body_iter():
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            yield chunk

    temp_path, size_bytes, sha = await stream_upload_to_temp(_body_iter())
    try:
        try:
            plan = await build_import_plan(
                temp_path=temp_path,
                original_filename=file.filename,
                sha256_hex=sha,
                size_bytes=size_bytes,
                name=name or None,
                display_name=display_name,
                catalogs=catalog_names,
                category=category or None,
                developer=developer or None,
                description=description or None,
                unattended_install=unattended_install,
                storage=storage,
                munki_repo_subdir=munki_repo_subdir or None,
            )
        except StorageNotConfiguredError as e:
            raise HTTPException(status_code=503, detail=str(e)) from e
        except ValueError as e:
            # ``sanitize_relative_path`` raises on path traversal / empty
            # segments after we combine ``pkgs/`` + subdir + filename.
            raise HTTPException(status_code=422, detail=str(e)) from e
    finally:
        cleanup_temp(temp_path)

    uploader_email = getattr(user, "email", None) or "unknown"
    pkg = PkgInfo(
        name=plan.name,
        display_name=plan.display_name,
        version=plan.version,
        description=plan.description,
        category=plan.category,
        developer=plan.developer,
        installer_item_location=plan.installer_item_location,
        installer_item_hash=plan.installer_item_hash,
        installer_item_size=plan.installer_item_size_kb,
        installer_type=plan.installer_type,
        unattended_install=plan.unattended_install,
        receipts=plan.receipts,
        minimum_os_version=plan.minimum_os_version,
        supported_architectures=plan.supported_architectures,
        pending_metadata=plan.pending_metadata,
        metadata_={
            "automunki_uploaded_by": uploader_email,
            "automunki_uploaded_at": datetime.now(UTC).isoformat(),
        },
    )
    session.add(pkg)
    await session.flush()

    for cat_name in plan.catalog_names:
        cat_row = (await session.execute(select(Catalog).where(Catalog.name == cat_name))).scalar_one_or_none()
        if cat_row is None:
            cat_row = Catalog(name=cat_name)
            session.add(cat_row)
            await session.flush()
        session.add(
            PkgInfoCatalog(
                pkg_info_id=pkg.id,
                catalog_id=cat_row.id,
                entered_at=datetime.now(UTC),
            )
        )

    await create_audit_entry(
        session,
        action="software.direct_upload",
        entity_type="pkginfo",
        entity_id=str(pkg.id),
        entity_name=f"{pkg.name} {pkg.version}",
        after_snapshot={
            "name": pkg.name,
            "version": pkg.version,
            "filename": file.filename,
            "size_bytes": size_bytes,
            "pending_metadata": plan.pending_metadata,
            "installer_item_location": pkg.installer_item_location,
        },
    )

    await session.commit()
    await session.refresh(pkg)

    return _pkg_to_read(pkg, plan.catalog_names)
