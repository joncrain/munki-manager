import uuid
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from automunki.api.deps import get_session
from automunki.core.security import current_optional_user
from automunki.models.autopkg import AutoPkgMetadataCacheEntry, AutoPkgRecipe
from automunki.models.client import ClientInstallReport
from automunki.models.munki import (
    PKGINFO_METADATA_RECIPE_IDENTIFIER_KEY,
    Catalog,
    PkgInfo,
    PkgInfoCatalog,
    ShardOverride,
    ShardRolloutStatus,
)
from automunki.models.user import User
from automunki.schemas.common import PaginatedResponse
from automunki.schemas.munki import (
    CatalogAssignment,
    PkgInfoBulkUpdate,
    PkgInfoBulkUpdateResult,
    PkgInfoPromotionQueueItemRead,
    PkgInfoPromotionStatusRead,
    PkgInfoRead,
    PkgInfoShardQueueItemRead,
    PkgInfoShardStatusRead,
    PkgInfoSummary,
    PkgInfoUpdate,
    PromoteRequest,
    ShardPercentOverrideRequest,
)
from automunki.services.audit import create_audit_entry
from automunki.services.loose_version import loose_version_key
from automunki.services.munki import compile_pkginfo_plist
from automunki.services.pkginfo_latest import (
    fetch_latest_version_by_name,
    is_latest_version,
)
from automunki.services.promotion import (
    build_pkginfo_channel_promotion_status,
    list_channel_promotion_queue_items,
    promote_pkginfo,
)
from automunki.services.shard_rollout import (
    build_shard_status,
    complete_shard_rollout,
    deployment_fields_for_software_name,
    fetch_manifest_names_for_items,
    list_shard_queue_items,
    maybe_init_shard_after_catalog_change,
    pause_shard_rollout,
    set_shard_percent_override,
    start_shard_rollout,
)


def _metadata_cache_key_candidates(recipe_identifier: str) -> list[str]:
    """Possible ``recipe_key`` values in ``autopkg_metadata_cache_entry``.

    cloud-autopkg-runner keys the JSON cache by **recipe file basename** (e.g.
    ``1Password.munki.recipe``), while pkginfo metadata stores the AutoPkg
    **Identifier** (e.g. ``local.munki.1Password``). Try both and the override
    name form via the DB row (``write_overrides`` uses ``{name}.munki.recipe``).
    """
    s = (recipe_identifier or "").strip()
    if not s:
        return []
    keys: list[str] = [s]
    if not s.endswith(".munki.recipe"):
        keys.append(f"{s}.munki.recipe")
    return keys


async def _delete_metadata_cache_entries_for_recipe(session: AsyncSession, recipe_identifier: str) -> int:
    """Delete cache rows for any key that may refer to this recipe. Returns row count."""
    keys = set(_metadata_cache_key_candidates(recipe_identifier))
    r = await session.execute(select(AutoPkgRecipe).where(AutoPkgRecipe.identifier == recipe_identifier.strip()))
    row = r.scalar_one_or_none()
    if row and (row.name or "").strip():
        keys.add(f"{row.name.strip()}.munki.recipe")
    deleted = 0
    for k in keys:
        result = await session.execute(
            delete(AutoPkgMetadataCacheEntry).where(AutoPkgMetadataCacheEntry.recipe_key == k)
        )
        deleted += int(result.rowcount or 0)
    return deleted


router = APIRouter(prefix="/pkginfo", tags=["pkginfo"])

INSTALL_REPORT_TIMELINE_DAYS = 90
INSTALL_REPORT_TIMELINE_MIN_DAYS = 7
INSTALL_REPORT_TIMELINE_MAX_DAYS = 90
UNKNOWN_INSTALL_VERSION = "(unknown)"


def _filled_daily_counts(
    rows: list[tuple[object, int]],
    days: int,
    *,
    end: date | None = None,
) -> list[dict[str, str | int]]:
    """Map SQL day buckets to a full calendar series including zeros."""
    counts: dict[date, int] = {}
    for dt, cnt in rows:
        if isinstance(dt, datetime):
            d = dt.astimezone(UTC).date()
        else:
            d = dt  # pragma: no cover
        counts[d] = int(cnt)

    end_date = end or datetime.now(UTC).date()
    start = end_date - timedelta(days=days - 1)
    series: list[dict[str, str | int]] = []
    cur = start
    while cur <= end_date:
        series.append({"date": cur.isoformat(), "count": counts.get(cur, 0)})
        cur += timedelta(days=1)
    return series


def _version_timeline_sort_key(version: str) -> tuple[int, tuple[object, ...] | str]:
    if version == UNKNOWN_INSTALL_VERSION:
        return (0, version)
    return (1, loose_version_key(version))


def _build_install_timeline_by_version(
    rows: list[tuple[object, str | None, int]],
    days: int,
    *,
    end: date | None = None,
) -> tuple[list[str], dict[str, list[dict[str, str | int]]]]:
    """Group install events by version and fill daily counts for each series."""
    by_version_day: dict[str, dict[date, int]] = {}
    for dt, version, cnt in rows:
        if isinstance(dt, datetime):
            d = dt.astimezone(UTC).date()
        else:
            d = dt  # pragma: no cover
        version_label = (version or "").strip() or UNKNOWN_INSTALL_VERSION
        by_version_day.setdefault(version_label, {})[d] = int(cnt)

    versions = sorted(by_version_day.keys(), key=_version_timeline_sort_key, reverse=True)
    end_date = end or datetime.now(UTC).date()
    start = end_date - timedelta(days=days - 1)

    timeline_by_version: dict[str, list[dict[str, str | int]]] = {}
    for version in versions:
        counts = by_version_day[version]
        series: list[dict[str, str | int]] = []
        cur = start
        while cur <= end_date:
            series.append({"date": cur.isoformat(), "count": counts.get(cur, 0)})
            cur += timedelta(days=1)
        timeline_by_version[version] = series

    return versions, timeline_by_version


async def _fetch_install_counts_by_name(
    session: AsyncSession,
    names: list[str],
) -> dict[str, int]:
    """Installed-status install report rows grouped by Munki item name."""
    if not names:
        return {}
    rows = (
        await session.execute(
            select(ClientInstallReport.item_name, func.count())
            .where(ClientInstallReport.item_name.in_(names))
            .where(ClientInstallReport.status == "installed")
            .group_by(ClientInstallReport.item_name)
        )
    ).all()
    return {name: int(cnt) for name, cnt in rows}


def _to_summary(
    pkg: PkgInfo,
    *,
    is_latest: bool = False,
    deployment_extra: dict | None = None,
    install_count: int = 0,
) -> dict:
    base = {
        "id": pkg.id,
        "name": pkg.name,
        "display_name": pkg.display_name,
        "icon_name": pkg.icon_name,
        "version": pkg.version,
        "category": pkg.category,
        "developer": pkg.developer,
        "catalog_names": [c.name for c in pkg.catalogs],
        "unattended_install": pkg.unattended_install,
        "unattended_uninstall": pkg.unattended_uninstall,
        "minimum_os_version": pkg.minimum_os_version,
        "installer_type": pkg.installer_type,
        "restart_action": pkg.restart_action,
        "pending_metadata": pkg.pending_metadata,
        "is_latest": is_latest,
        "install_count": install_count,
        "created_at": pkg.created_at,
        "updated_at": pkg.updated_at,
    }
    if deployment_extra:
        base.update(deployment_extra)
    else:
        base.update(
            {
                "deployment_status": "not_in_production",
                "shard_percent": None,
                "is_first_production_deploy": False,
                "in_manifest": False,
            }
        )
    return base


def _to_read(pkg: PkgInfo) -> dict:
    data = {
        "id": pkg.id,
        "name": pkg.name,
        "version": pkg.version,
        "display_name": pkg.display_name,
        "description": pkg.description,
        "category": pkg.category,
        "developer": pkg.developer,
        "icon_name": pkg.icon_name,
        "installer_item_location": pkg.installer_item_location,
        "installer_item_hash": pkg.installer_item_hash,
        "installer_item_size": pkg.installer_item_size,
        "installed_size": pkg.installed_size,
        "installer_type": pkg.installer_type,
        "minimum_os_version": pkg.minimum_os_version,
        "maximum_os_version": pkg.maximum_os_version,
        "uninstall_method": pkg.uninstall_method,
        "unattended_install": pkg.unattended_install,
        "unattended_uninstall": pkg.unattended_uninstall,
        "autoremove": pkg.autoremove,
        "uninstallable": pkg.uninstallable,
        "installs": pkg.installs,
        "receipts": pkg.receipts,
        "blocking_applications": pkg.blocking_applications,
        "items_to_copy": pkg.items_to_copy,
        "supported_architectures": pkg.supported_architectures,
        "requires": pkg.requires,
        "update_for": pkg.update_for,
        "preinstall_script": pkg.preinstall_script,
        "postinstall_script": pkg.postinstall_script,
        "preuninstall_script": pkg.preuninstall_script,
        "postuninstall_script": pkg.postuninstall_script,
        "installcheck_script": pkg.installcheck_script,
        "uninstallcheck_script": pkg.uninstallcheck_script,
        "version_script": pkg.version_script,
        "notes": pkg.notes,
        "restart_action": pkg.restart_action,
        "on_demand": pkg.on_demand,
        "force_install_after_date": pkg.force_install_after_date,
        "apple_item": pkg.apple_item,
        "installable_condition": pkg.installable_condition,
        "package_path": pkg.package_path,
        "package_complete_url": pkg.package_complete_url,
        "minimum_munki_version": pkg.minimum_munki_version,
        "uninstaller_item_location": pkg.uninstaller_item_location,
        "catalog_names": [c.name for c in pkg.catalogs],
        "is_deleted": pkg.is_deleted,
        "pending_metadata": pkg.pending_metadata,
        "auto_promote": pkg.auto_promote,
        "promotion_channel_id": pkg.promotion_channel_id,
        "created_at": pkg.created_at,
        "updated_at": pkg.updated_at,
    }
    return data


async def _deployment_extra_for_pkginfos(
    session: AsyncSession,
    pkginfos: list[PkgInfo],
) -> dict[uuid.UUID, dict]:
    if not pkginfos:
        return {}
    names = list({p.name for p in pkginfos})
    in_manifest_names = await fetch_manifest_names_for_items(session, set(names))
    name_fields: dict[str, dict] = {}
    for name in names:
        name_fields[name] = await deployment_fields_for_software_name(
            session,
            name,
            in_manifest=name in in_manifest_names,
        )
    return {pkg.id: name_fields[pkg.name] for pkg in pkginfos}


def _matches_deployment_filter(deployment_status: str, filt: str) -> bool:
    return deployment_status == filt


@router.get("", response_model=PaginatedResponse)
async def list_pkginfo(
    session: AsyncSession = Depends(get_session),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    search: str | None = None,
    catalog: str | None = None,
    category: str | None = None,
    name: str | None = None,
    latest_only: bool = False,
    deployment_status: str | None = None,
    sort_by: str = "name",
    sort_order: str = "asc",
):
    query = select(PkgInfo).where(PkgInfo.is_deleted.is_(False))

    if search:
        query = query.where(PkgInfo.name.ilike(f"%{search}%") | PkgInfo.display_name.ilike(f"%{search}%"))
    if category:
        query = query.where(PkgInfo.category == category)
    if name:
        query = query.where(PkgInfo.name == name)
    if catalog:
        query = query.join(PkgInfoCatalog).join(Catalog).where(Catalog.name == catalog)

    latest_by_name = await fetch_latest_version_by_name(session)

    if latest_only:
        matching = await session.execute(query.with_only_columns(PkgInfo.id, PkgInfo.name, PkgInfo.version))
        latest_ids = [row.id for row in matching.all() if is_latest_version(row.name, row.version, latest_by_name)]
        if not latest_ids:
            return PaginatedResponse(
                items=[],
                total=0,
                page=page,
                page_size=page_size,
                total_pages=0,
            )
        query = query.where(PkgInfo.id.in_(latest_ids))

    if deployment_status:
        result = await session.execute(query.options(selectinload(PkgInfo.catalogs)))
        all_pkgs = list(result.scalars().unique().all())
        deploy_extra = await _deployment_extra_for_pkginfos(session, all_pkgs)
        filtered = [
            p
            for p in all_pkgs
            if _matches_deployment_filter(deploy_extra[p.id]["deployment_status"], deployment_status)
        ]
        total = len(filtered)
        install_counts = await _fetch_install_counts_by_name(session, list({p.name for p in filtered}))
        if sort_by == "version":
            reverse = sort_order != "asc"
            filtered.sort(key=lambda p: loose_version_key(p.version), reverse=reverse)
        elif sort_by == "install_count":
            reverse = sort_order != "asc"
            filtered.sort(
                key=lambda p: (install_counts.get(p.name, 0), p.name or ""),
                reverse=reverse,
            )
        else:
            sort_col_name = (
                sort_by if sort_by in ("name", "version", "category", "updated_at", "created_at") else "name"
            )
            reverse = sort_order != "asc"
            filtered.sort(
                key=lambda p: getattr(p, sort_col_name, p.name) or "",
                reverse=reverse,
            )
        page_pkgs = filtered[(page - 1) * page_size : page * page_size]
        page_deploy = {p.id: deploy_extra[p.id] for p in page_pkgs}
        items = [
            PkgInfoSummary(
                **_to_summary(
                    p,
                    is_latest=is_latest_version(p.name, p.version, latest_by_name),
                    deployment_extra=page_deploy[p.id],
                    install_count=install_counts.get(p.name, 0),
                )
            )
            for p in page_pkgs
        ]
        return PaginatedResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=(total + page_size - 1) // page_size if total else 0,
        )

    count_query = select(func.count()).select_from(query.subquery())
    total = (await session.execute(count_query)).scalar() or 0

    if sort_by == "version":
        id_version_result = await session.execute(query.with_only_columns(PkgInfo.id, PkgInfo.version))
        id_version_rows = id_version_result.all()
        reverse = sort_order != "asc"
        sorted_rows = sorted(
            id_version_rows,
            key=lambda row: loose_version_key(row.version),
            reverse=reverse,
        )
        page_rows = sorted_rows[(page - 1) * page_size : page * page_size]
        page_ids = [row.id for row in page_rows]
        if not page_ids:
            items = []
        else:
            page_result = await session.execute(
                select(PkgInfo).where(PkgInfo.id.in_(page_ids)).options(selectinload(PkgInfo.catalogs))
            )
            pkg_by_id = {p.id: p for p in page_result.scalars().unique().all()}
            page_pkgs = [pkg_by_id[pid] for pid in page_ids if pid in pkg_by_id]
            deploy_extra = await _deployment_extra_for_pkginfos(session, page_pkgs)
            install_counts = await _fetch_install_counts_by_name(session, list({p.name for p in page_pkgs}))
            items = [
                PkgInfoSummary(
                    **_to_summary(
                        pkg_by_id[pkg_id],
                        is_latest=is_latest_version(
                            pkg_by_id[pkg_id].name,
                            pkg_by_id[pkg_id].version,
                            latest_by_name,
                        ),
                        deployment_extra=deploy_extra.get(pkg_id),
                        install_count=install_counts.get(pkg_by_id[pkg_id].name, 0),
                    )
                )
                for pkg_id in page_ids
                if pkg_id in pkg_by_id
            ]
    elif sort_by == "install_count":
        id_name_result = await session.execute(query.with_only_columns(PkgInfo.id, PkgInfo.name))
        id_name_rows = id_name_result.all()
        install_counts = await _fetch_install_counts_by_name(session, list({row.name for row in id_name_rows}))
        reverse = sort_order != "asc"
        sorted_rows = sorted(
            id_name_rows,
            key=lambda row: (install_counts.get(row.name, 0), row.name or ""),
            reverse=reverse,
        )
        page_rows = sorted_rows[(page - 1) * page_size : page * page_size]
        page_ids = [row.id for row in page_rows]
        if not page_ids:
            items = []
        else:
            page_result = await session.execute(
                select(PkgInfo).where(PkgInfo.id.in_(page_ids)).options(selectinload(PkgInfo.catalogs))
            )
            pkg_by_id = {p.id: p for p in page_result.scalars().unique().all()}
            page_pkgs = [pkg_by_id[pid] for pid in page_ids if pid in pkg_by_id]
            deploy_extra = await _deployment_extra_for_pkginfos(session, page_pkgs)
            items = [
                PkgInfoSummary(
                    **_to_summary(
                        pkg_by_id[pkg_id],
                        is_latest=is_latest_version(
                            pkg_by_id[pkg_id].name,
                            pkg_by_id[pkg_id].version,
                            latest_by_name,
                        ),
                        deployment_extra=deploy_extra.get(pkg_id),
                        install_count=install_counts.get(pkg_by_id[pkg_id].name, 0),
                    )
                )
                for pkg_id in page_ids
                if pkg_id in pkg_by_id
            ]
    else:
        sort_col = getattr(PkgInfo, sort_by, PkgInfo.name)
        query = query.order_by(sort_col.asc() if sort_order == "asc" else sort_col.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        query = query.options(selectinload(PkgInfo.catalogs))

        result = await session.execute(query)
        page_pkgs = list(result.scalars().unique().all())
        deploy_extra = await _deployment_extra_for_pkginfos(session, page_pkgs)
        install_counts = await _fetch_install_counts_by_name(session, list({p.name for p in page_pkgs}))
        items = [
            PkgInfoSummary(
                **_to_summary(
                    p,
                    is_latest=is_latest_version(p.name, p.version, latest_by_name),
                    deployment_extra=deploy_extra.get(p.id),
                    install_count=install_counts.get(p.name, 0),
                )
            )
            for p in page_pkgs
        ]

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size if total else 0,
    )


@router.get("/categories", response_model=list[str])
async def list_categories(
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(PkgInfo.category)
        .where(PkgInfo.is_deleted.is_(False), PkgInfo.category.isnot(None))
        .distinct()
        .order_by(PkgInfo.category)
    )
    return [row[0] for row in result.all()]


@router.get("/promotion-queue", response_model=list[PkgInfoPromotionQueueItemRead])
async def get_promotion_queue(
    limit: int = Query(20, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
):
    """Versions on a channel with auto-promote, in a path source catalog, with the next move + status."""
    rows = await list_channel_promotion_queue_items(session, limit=limit)
    return [PkgInfoPromotionQueueItemRead(**r) for r in rows]


@router.get("/shard-queue", response_model=list[PkgInfoShardQueueItemRead])
async def get_shard_queue(
    limit: int = Query(20, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
):
    """Production shard rollouts: pending approval, active sharding, or paused."""
    rows = await list_shard_queue_items(session, limit=limit)
    return [PkgInfoShardQueueItemRead(**r) for r in rows]


@router.post("/bulk-update", response_model=PkgInfoBulkUpdateResult)
async def bulk_update_pkginfo(
    data: PkgInfoBulkUpdate,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(current_optional_user),
):
    """Apply the same category and/or catalog list to many pkginfo records."""
    payload = data.model_dump(exclude_unset=True)
    pkginfo_ids = payload.pop("pkginfo_ids")
    if not payload:
        raise HTTPException(
            status_code=400,
            detail="Include at least one of: category, catalog_names",
        )

    updated = 0
    for pkg_id in pkginfo_ids:
        result = await session.execute(
            select(PkgInfo).options(selectinload(PkgInfo.catalogs)).where(PkgInfo.id == pkg_id)
        )
        pkg = result.scalar_one_or_none()
        if not pkg or pkg.is_deleted:
            continue

        before = _to_read(pkg)
        before_names = [c.name for c in pkg.catalogs]
        changes: dict = {}

        if "category" in payload:
            pkg.category = payload["category"]
            changes["category"] = {"before": before.get("category"), "after": payload["category"]}

        if "catalog_names" in payload:
            names = payload["catalog_names"]
            await session.execute(PkgInfoCatalog.__table__.delete().where(PkgInfoCatalog.pkg_info_id == pkg_id))
            await session.flush()
            for cat_name in names:
                cat_result = await session.execute(select(Catalog).where(Catalog.name == cat_name))
                cat = cat_result.scalar_one_or_none()
                if cat:
                    session.add(
                        PkgInfoCatalog(
                            pkg_info_id=pkg_id,
                            catalog_id=cat.id,
                            entered_at=datetime.now(UTC),
                        )
                    )
            await session.flush()
            changes["catalog_names"] = {"before": before_names, "after": names}
            await maybe_init_shard_after_catalog_change(
                session, pkg_id, user_email=user.email if user else "system:shard-rollout"
            )

        reload = await session.execute(
            select(PkgInfo).options(selectinload(PkgInfo.catalogs)).where(PkgInfo.id == pkg_id)
        )
        pkg = reload.scalar_one()
        after = _to_read(pkg)

        await create_audit_entry(
            session,
            action="update",
            entity_type="pkg_info",
            entity_id=str(pkg_id),
            entity_name=f"{pkg.name} {pkg.version}",
            user_id=user.id if user else None,
            user_email=user.email if user else None,
            before_snapshot=before,
            after_snapshot=after,
            changes=changes,
        )
        updated += 1

    await session.commit()
    return PkgInfoBulkUpdateResult(updated=updated)


@router.get("/{pkg_id}", response_model=PkgInfoRead)
async def get_pkginfo(
    pkg_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(PkgInfo).options(selectinload(PkgInfo.catalogs)).where(PkgInfo.id == pkg_id))
    pkg = result.scalar_one_or_none()
    if not pkg:
        raise HTTPException(status_code=404, detail="PkgInfo not found")
    return PkgInfoRead(**_to_read(pkg))


@router.get("/{pkg_id}/promotion-status", response_model=PkgInfoPromotionStatusRead)
async def get_pkginfo_promotion_status(
    pkg_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    """Dwell and upcoming catalog moves for this version (from ``munki_pkginfo`` + channel; no recipe)."""
    result = await session.execute(select(PkgInfo).options(selectinload(PkgInfo.catalogs)).where(PkgInfo.id == pkg_id))
    pkg = result.scalar_one_or_none()
    if not pkg or pkg.is_deleted:
        raise HTTPException(status_code=404, detail="PkgInfo not found")
    raw = await build_pkginfo_channel_promotion_status(session, pkg)
    return PkgInfoPromotionStatusRead(**raw)


@router.get("/{pkg_id}/shard-status", response_model=PkgInfoShardStatusRead)
async def get_pkginfo_shard_status(
    pkg_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(PkgInfo).options(selectinload(PkgInfo.catalogs)).where(PkgInfo.id == pkg_id))
    pkg = result.scalar_one_or_none()
    if not pkg or pkg.is_deleted:
        raise HTTPException(status_code=404, detail="PkgInfo not found")
    raw = await build_shard_status(session, pkg)
    return PkgInfoShardStatusRead(**raw)


@router.post("/{pkg_id}/shard/start")
async def start_pkginfo_shard_rollout(
    pkg_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(current_optional_user),
):
    result = await session.execute(select(PkgInfo).options(selectinload(PkgInfo.catalogs)).where(PkgInfo.id == pkg_id))
    pkg = result.scalar_one_or_none()
    if not pkg or pkg.is_deleted:
        raise HTTPException(status_code=404, detail="PkgInfo not found")
    try:
        await start_shard_rollout(
            session,
            pkg,
            user_id=user.id if user else None,
            user_email=user.email if user else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    await session.commit()
    return {"message": "Production shard rollout started"}


@router.post("/{pkg_id}/shard/pause")
async def pause_pkginfo_shard_rollout(
    pkg_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(current_optional_user),
):
    result = await session.execute(select(PkgInfo).options(selectinload(PkgInfo.catalogs)).where(PkgInfo.id == pkg_id))
    pkg = result.scalar_one_or_none()
    if not pkg or pkg.is_deleted:
        raise HTTPException(status_code=404, detail="PkgInfo not found")
    await pause_shard_rollout(
        session,
        pkg,
        user_id=user.id if user else None,
        user_email=user.email if user else None,
    )
    await session.commit()
    return {"message": "Production shard rollout paused"}


@router.post("/{pkg_id}/shard/complete")
async def complete_pkginfo_shard_rollout(
    pkg_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(current_optional_user),
):
    result = await session.execute(select(PkgInfo).options(selectinload(PkgInfo.catalogs)).where(PkgInfo.id == pkg_id))
    pkg = result.scalar_one_or_none()
    if not pkg or pkg.is_deleted:
        raise HTTPException(status_code=404, detail="PkgInfo not found")
    await complete_shard_rollout(
        session,
        pkg,
        user_id=user.id if user else None,
        user_email=user.email if user else None,
    )
    await session.commit()
    return {"message": "Production shard rollout completed"}


@router.put("/{pkg_id}/shard/override", response_model=PkgInfoShardStatusRead)
async def set_pkginfo_shard_override(
    pkg_id: uuid.UUID,
    data: ShardPercentOverrideRequest,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(current_optional_user),
):
    result = await session.execute(select(PkgInfo).options(selectinload(PkgInfo.catalogs)).where(PkgInfo.id == pkg_id))
    pkg = result.scalar_one_or_none()
    if not pkg or pkg.is_deleted:
        raise HTTPException(status_code=404, detail="PkgInfo not found")
    try:
        await set_shard_percent_override(
            session,
            pkg,
            data.shard_percent,
            user_id=user.id if user else None,
            user_email=user.email if user else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    await session.commit()
    raw = await build_shard_status(session, pkg)
    return PkgInfoShardStatusRead(**raw)


@router.get("/{pkg_id}/plist")
async def get_pkginfo_plist(
    pkg_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(PkgInfo).options(selectinload(PkgInfo.catalogs)).where(PkgInfo.id == pkg_id))
    pkg = result.scalar_one_or_none()
    if not pkg:
        raise HTTPException(status_code=404, detail="PkgInfo not found")
    plist_data = await compile_pkginfo_plist(pkg)
    return Response(content=plist_data, media_type="application/xml")


@router.get("/{pkg_id}/install-reports/summary")
async def pkginfo_install_reports_summary(
    pkg_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    days: int = Query(
        INSTALL_REPORT_TIMELINE_DAYS,
        ge=INSTALL_REPORT_TIMELINE_MIN_DAYS,
        le=INSTALL_REPORT_TIMELINE_MAX_DAYS,
        description="Number of calendar days for activity timelines",
    ),
):
    """Counts by status, distinct machines, and daily install events for this pkginfo name."""
    result = await session.execute(select(PkgInfo).where(PkgInfo.id == pkg_id))
    pkg = result.scalar_one_or_none()
    if not pkg:
        raise HTTPException(status_code=404, detail="PkgInfo not found")

    name = pkg.name

    total_reports = (
        await session.scalar(
            select(func.count()).select_from(ClientInstallReport).where(ClientInstallReport.item_name == name)
        )
    ) or 0

    unique_machines = (
        await session.scalar(
            select(func.count(func.distinct(ClientInstallReport.machine_id)))
            .select_from(ClientInstallReport)
            .where(ClientInstallReport.item_name == name)
        )
    ) or 0

    status_rows = (
        await session.execute(
            select(ClientInstallReport.status, func.count())
            .where(ClientInstallReport.item_name == name)
            .group_by(ClientInstallReport.status)
        )
    ).all()
    by_status = {row[0]: int(row[1]) for row in status_rows}

    event_ts = func.coalesce(ClientInstallReport.install_date, ClientInstallReport.created_at)
    cutoff = datetime.now(UTC) - timedelta(days=days - 1)
    day_trunc = func.date_trunc("day", event_ts)
    version_expr = func.coalesce(ClientInstallReport.item_version, UNKNOWN_INSTALL_VERSION)

    timeline_rows = (
        await session.execute(
            select(day_trunc, func.count(ClientInstallReport.id))
            .where(ClientInstallReport.item_name == name)
            .where(event_ts >= cutoff)
            .group_by(day_trunc)
            .order_by(day_trunc)
        )
    ).all()

    version_timeline_rows = (
        await session.execute(
            select(day_trunc, version_expr, func.count(ClientInstallReport.id))
            .where(ClientInstallReport.item_name == name)
            .where(event_ts >= cutoff)
            .group_by(day_trunc, version_expr)
            .order_by(day_trunc, version_expr)
        )
    ).all()

    versions, timeline_by_version = _build_install_timeline_by_version(version_timeline_rows, days)

    return {
        "item_name": name,
        "total_reports": total_reports,
        "unique_machines": unique_machines,
        "by_status": by_status,
        "days": days,
        "versions": versions,
        "timeline_by_version": timeline_by_version,
        "timeline": _filled_daily_counts(timeline_rows, days),
    }


@router.put("/{pkg_id}", response_model=PkgInfoRead)
async def update_pkginfo(
    pkg_id: uuid.UUID,
    data: PkgInfoUpdate,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(current_optional_user),
):
    result = await session.execute(select(PkgInfo).options(selectinload(PkgInfo.catalogs)).where(PkgInfo.id == pkg_id))
    pkg = result.scalar_one_or_none()
    if not pkg:
        raise HTTPException(status_code=404, detail="PkgInfo not found")

    before = _to_read(pkg)
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(pkg, field, value)
    if "installable_condition" in update_data:
        pkg.shard_rollout_status = ShardRolloutStatus.paused
        pkg.shard_override = ShardOverride.pause

    await create_audit_entry(
        session,
        action="update",
        entity_type="pkg_info",
        entity_id=str(pkg_id),
        entity_name=f"{pkg.name} {pkg.version}",
        user_id=user.id if user else None,
        user_email=user.email if user else None,
        before_snapshot=before,
        after_snapshot=_to_read(pkg),
        changes=update_data,
    )

    await session.commit()
    await session.refresh(pkg)
    return PkgInfoRead(**_to_read(pkg))


@router.delete("/{pkg_id}")
async def delete_pkginfo(
    pkg_id: uuid.UUID,
    clear_metadata_cache: bool = Query(
        False,
        description=(
            "If true, remove the cloud AutoPkg metadata cache row(s) for this recipe. "
            "Keys match cloud-autopkg-runner (e.g. Name.munki.recipe) and the stored "
            "recipe identifier, resolved via the autopkg_recipe table when present."
        ),
    ),
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(current_optional_user),
):
    pkg = await session.get(PkgInfo, pkg_id)
    if not pkg:
        raise HTTPException(status_code=404, detail="PkgInfo not found")

    cache_deleted = 0
    if clear_metadata_cache and isinstance(pkg.metadata_, dict):
        recipe_id = pkg.metadata_.get(PKGINFO_METADATA_RECIPE_IDENTIFIER_KEY)
        if isinstance(recipe_id, str) and recipe_id.strip():
            cache_deleted = await _delete_metadata_cache_entries_for_recipe(session, recipe_id.strip())

    pkg.is_deleted = True
    await create_audit_entry(
        session,
        action="delete",
        entity_type="pkg_info",
        entity_id=str(pkg_id),
        entity_name=f"{pkg.name} {pkg.version}",
        user_id=user.id if user else None,
        user_email=user.email if user else None,
    )
    await session.commit()
    return {
        "message": "PkgInfo deleted",
        "metadata_cache_entries_deleted": cache_deleted,
    }


@router.put("/{pkg_id}/catalogs", response_model=PkgInfoRead)
async def update_pkginfo_catalogs(
    pkg_id: uuid.UUID,
    data: CatalogAssignment,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(current_optional_user),
):
    result = await session.execute(select(PkgInfo).options(selectinload(PkgInfo.catalogs)).where(PkgInfo.id == pkg_id))
    pkg = result.scalar_one_or_none()
    if not pkg:
        raise HTTPException(status_code=404, detail="PkgInfo not found")

    before_names = [c.name for c in pkg.catalogs]

    await session.execute(PkgInfoCatalog.__table__.delete().where(PkgInfoCatalog.pkg_info_id == pkg_id))
    await session.flush()

    for cat_name in data.catalog_names:
        cat_result = await session.execute(select(Catalog).where(Catalog.name == cat_name))
        cat = cat_result.scalar_one_or_none()
        if cat:
            session.add(
                PkgInfoCatalog(
                    pkg_info_id=pkg_id,
                    catalog_id=cat.id,
                    entered_at=datetime.now(UTC),
                )
            )

    await session.flush()
    result = await session.execute(select(PkgInfo).options(selectinload(PkgInfo.catalogs)).where(PkgInfo.id == pkg_id))
    pkg = result.scalar_one()

    await maybe_init_shard_after_catalog_change(
        session, pkg_id, user_email=user.email if user else "system:shard-rollout"
    )

    await create_audit_entry(
        session,
        action="update",
        entity_type="pkg_info",
        entity_id=str(pkg_id),
        entity_name=f"{pkg.name} {pkg.version}",
        user_id=user.id if user else None,
        user_email=user.email if user else None,
        changes={"catalog_names": {"before": before_names, "after": data.catalog_names}},
    )

    await session.commit()
    result = await session.execute(select(PkgInfo).options(selectinload(PkgInfo.catalogs)).where(PkgInfo.id == pkg_id))
    pkg = result.scalar_one_or_none()
    return PkgInfoRead(**_to_read(pkg))


@router.post("/{pkg_id}/promote")
async def promote_pkg(
    pkg_id: uuid.UUID,
    data: PromoteRequest,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(current_optional_user),
):
    success = await promote_pkginfo(
        session,
        pkg_info_id=pkg_id,
        target_catalog_id=data.target_catalog_id,
        user_id=user.id if user else None,
        user_email=user.email if user else None,
    )
    if not success:
        raise HTTPException(status_code=404, detail="PkgInfo or catalog not found")
    await session.commit()
    return {"message": "Promoted successfully"}
