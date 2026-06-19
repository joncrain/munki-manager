"""Extended insight handlers: catalog age, adoption curves, AutoPkg cadence, hardware filters."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from automunki.models.autopkg import AutoPkgRecipe, AutoPkgRunResult, RecipeResultStatus
from automunki.models.client import ClientInstallReport, ClientMachine
from automunki.models.munki import Catalog, PkgInfo, PkgInfoCatalog
from automunki.services.insights.handlers import (
    _find_installed_version,
    _resolve_catalog_item_name,
    get_catalog_latest_version,
)
from automunki.services.insights.hardware_match import machine_matches_hardware
from automunki.services.insights.machine_activity import DEFAULT_ACTIVE_WITHIN_DAYS, apply_active_machine_filter
from automunki.services.insights.software_resolve import expand_software_matchers
from automunki.services.loose_version import compare_loose_versions


def _days_since(dt: datetime | None, *, now: datetime | None = None) -> float | None:
    if dt is None:
        return None
    ref = now or datetime.now(UTC)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return round((ref - dt).total_seconds() / 86400, 1)


def _coalesce_install_ts(install_date: datetime | None, created_at: datetime) -> datetime:
    if install_date is not None:
        if install_date.tzinfo is None:
            return install_date.replace(tzinfo=UTC)
        return install_date
    if created_at.tzinfo is None:
        return created_at.replace(tzinfo=UTC)
    return created_at


async def get_pkginfo_update_age(
    session: AsyncSession,
    *,
    query: str | None = None,
    item_name: str | None = None,
) -> dict[str, Any]:
    """How long since the latest catalog version of software was added or updated."""
    hint = (query or item_name or "").strip()
    if not hint:
        return {"error": "Provide query or item_name"}

    catalog = await get_catalog_latest_version(session, query=hint, item_name=item_name)
    latest = catalog.get("latest_version")
    name = catalog.get("item_name")
    if not latest or not name:
        return {"error": f"No pkginfo found for {hint!r}", "query": hint}

    pkg_row = (
        await session.execute(
            select(PkgInfo).where(
                PkgInfo.name == name,
                PkgInfo.version == latest,
                PkgInfo.is_deleted.is_(False),
            )
        )
    ).scalar_one_or_none()

    if pkg_row is None:
        return {"error": f"Pkginfo row missing for {name} {latest}"}

    catalog_entries = (
        await session.execute(
            select(Catalog.name, PkgInfoCatalog.entered_at)
            .join(Catalog, PkgInfoCatalog.catalog_id == Catalog.id)
            .where(PkgInfoCatalog.pkg_info_id == pkg_row.id)
            .order_by(PkgInfoCatalog.entered_at.asc())
        )
    ).all()

    now = datetime.now(UTC)
    earliest_catalog_entry = catalog_entries[0][1] if catalog_entries else None

    return {
        "item_name": name,
        "display_name": catalog.get("display_name"),
        "latest_version": latest,
        "days_since_pkginfo_created": _days_since(pkg_row.created_at, now=now),
        "days_since_pkginfo_updated": _days_since(pkg_row.updated_at, now=now),
        "days_since_first_catalog_entry": _days_since(earliest_catalog_entry, now=now),
        "pkginfo_created_at": pkg_row.created_at.isoformat() if pkg_row.created_at else None,
        "pkginfo_updated_at": pkg_row.updated_at.isoformat() if pkg_row.updated_at else None,
        "catalog_memberships": [
            {"catalog": cat_name, "entered_at": entered.isoformat()} for cat_name, entered in catalog_entries
        ],
    }


async def get_adoption_timeline(
    session: AsyncSession,
    *,
    query: str | None = None,
    item_name: str | None = None,
    version: str | None = None,
    threshold_percent: float = 80.0,
    days_back: int = 365,
) -> dict[str, Any]:
    """Time to reach a fleet adoption threshold for a software version (from install reports)."""
    hint = (query or item_name or "").strip()
    if not hint:
        return {"error": "Provide query or item_name"}

    catalog = await get_catalog_latest_version(session, query=hint, item_name=item_name)
    target_version = version or catalog.get("latest_version")
    name = catalog.get("item_name")
    if not target_version or not name:
        return {"error": f"No catalog version found for {hint!r}"}

    pkg_row = (
        await session.execute(
            select(PkgInfo).where(
                PkgInfo.name == name,
                PkgInfo.version == target_version,
                PkgInfo.is_deleted.is_(False),
            )
        )
    ).scalar_one_or_none()

    release_at: datetime | None = None
    if pkg_row:
        release_at = pkg_row.created_at
        cat_entry = (
            await session.execute(
                select(func.min(PkgInfoCatalog.entered_at)).where(PkgInfoCatalog.pkg_info_id == pkg_row.id)
            )
        ).scalar_one_or_none()
        if cat_entry and (release_at is None or cat_entry < release_at):
            release_at = cat_entry

    cutoff = datetime.now(UTC) - timedelta(days=max(1, days_back))
    install_rows = (
        await session.execute(
            select(
                ClientInstallReport.machine_id,
                ClientInstallReport.install_date,
                ClientInstallReport.created_at,
            ).where(
                ClientInstallReport.item_name == name,
                ClientInstallReport.item_version == target_version,
                ClientInstallReport.status == "installed",
            )
        )
    ).all()

    first_by_machine: dict[Any, datetime] = {}
    for machine_id, install_date, created_at in install_rows:
        ts = _coalesce_install_ts(install_date, created_at)
        if ts < cutoff:
            continue
        prev = first_by_machine.get(machine_id)
        if prev is None or ts < prev:
            first_by_machine[machine_id] = ts

    sorted_installs = sorted(first_by_machine.values())
    total_fleet = (await session.execute(select(func.count()).select_from(ClientMachine))).scalar() or 0

    machines_ever_had_item = (
        await session.execute(
            select(func.count(func.distinct(ClientInstallReport.machine_id))).where(
                ClientInstallReport.item_name == name,
                ClientInstallReport.status == "installed",
            )
        )
    ).scalar() or 0

    denominator = total_fleet if total_fleet > 0 else machines_ever_had_item
    threshold_count = int((threshold_percent / 100.0) * denominator) if denominator else 0
    if threshold_count < 1 and sorted_installs:
        threshold_count = 1

    reached_at: datetime | None = None
    if threshold_count > 0 and len(sorted_installs) >= threshold_count:
        reached_at = sorted_installs[threshold_count - 1]

    current_adopted = len(first_by_machine)
    current_percent = round((current_adopted / denominator * 100) if denominator else 0, 1)

    days_to_threshold: float | None = None
    if release_at and reached_at:
        if release_at.tzinfo is None:
            release_at = release_at.replace(tzinfo=UTC)
        days_to_threshold = round((reached_at - release_at).total_seconds() / 86400, 1)

    return {
        "item_name": name,
        "version": target_version,
        "threshold_percent": threshold_percent,
        "fleet_denominator": denominator,
        "total_fleet_machines": total_fleet,
        "machines_ever_installed_item": machines_ever_had_item,
        "machines_on_target_version": current_adopted,
        "current_adoption_percent": current_percent,
        "threshold_reached": reached_at is not None,
        "days_to_threshold": days_to_threshold,
        "reached_at": reached_at.isoformat() if reached_at else None,
        "release_available_at": release_at.isoformat() if release_at else None,
        "note": (
            "Adoption is based on first install report per machine for this version. "
            "Denominator is total enrolled machines."
        ),
    }


async def get_autopkg_release_history(
    session: AsyncSession,
    *,
    query: str | None = None,
    item_name: str | None = None,
    days_back: int = 365,
    limit: int = 50,
) -> dict[str, Any]:
    """AutoPkg import history and release cadence for a software title."""
    hint = (query or item_name or "").strip()
    if not hint:
        return {"error": "Provide query or item_name"}

    name = await _resolve_catalog_item_name(session, hint)

    recipe_names: set[str] = {name}
    recipe_rows = (
        await session.execute(
            select(AutoPkgRecipe.name, AutoPkgRecipe.identifier).where(
                or_(
                    AutoPkgRecipe.name == name,
                    AutoPkgRecipe.name.ilike(f"%{name}%"),
                    AutoPkgRecipe.identifier.ilike(f"%{name.lower()}%"),
                )
            )
        )
    ).all()
    for rname, ident in recipe_rows:
        recipe_names.add(rname)
        if ident:
            recipe_names.add(ident)

    cutoff = datetime.now(UTC) - timedelta(days=max(1, days_back))
    name_filters = [AutoPkgRunResult.recipe_name.in_(recipe_names)]
    for rn in list(recipe_names):
        name_filters.append(AutoPkgRunResult.recipe_name.ilike(f"%{rn}%"))
        name_filters.append(AutoPkgRunResult.recipe_identifier.ilike(f"%{rn}%"))

    all_results = (
        await session.execute(
            select(
                AutoPkgRunResult.created_at,
                AutoPkgRunResult.status,
                AutoPkgRunResult.imported_version,
                AutoPkgRunResult.recipe_name,
            )
            .where(or_(*name_filters), AutoPkgRunResult.created_at >= cutoff)
            .order_by(AutoPkgRunResult.created_at.desc())
            .limit(max(limit * 4, 100))
        )
    ).all()

    imports = [row for row in all_results if row.status == RecipeResultStatus.imported and row.imported_version]
    imports_chrono = sorted(imports[:limit], key=lambda row: row.created_at or datetime.min.replace(tzinfo=UTC))

    intervals_days: list[float] = []
    for i in range(1, len(imports_chrono)):
        a = imports_chrono[i - 1].created_at
        b = imports_chrono[i].created_at
        if a and b:
            if a.tzinfo is None:
                a = a.replace(tzinfo=UTC)
            if b.tzinfo is None:
                b = b.replace(tzinfo=UTC)
            intervals_days.append((b - a).total_seconds() / 86400)

    avg_interval = round(sum(intervals_days) / len(intervals_days), 1) if intervals_days else None
    run_count = len(all_results)
    import_count = len(imports)
    no_change_count = sum(1 for r in all_results if r.status == RecipeResultStatus.no_change)

    rows = [
        [
            r.created_at.isoformat() if r.created_at else None,
            r.imported_version,
            r.recipe_name,
        ]
        for r in imports_chrono
    ]

    return {
        "item_name": name,
        "query": hint,
        "days_back": days_back,
        "autopkg_runs_matched": run_count,
        "new_version_imports": import_count,
        "no_change_results": no_change_count,
        "import_rate_percent": round((import_count / run_count * 100) if run_count else 0, 1),
        "average_days_between_imports": avg_interval,
        "median_days_between_imports": (
            round(sorted(intervals_days)[len(intervals_days) // 2], 1) if intervals_days else None
        ),
        "releases": [
            {
                "imported_at": r.created_at.isoformat() if r.created_at else None,
                "version": r.imported_version,
                "recipe_name": r.recipe_name,
            }
            for r in imports_chrono
        ],
        "table": {
            "columns": ["imported_at", "version", "recipe_name"],
            "rows": rows,
        },
    }


async def count_machines_with_software(
    session: AsyncSession,
    *,
    query: str | None = None,
    item_name: str | None = None,
    app_name: str | None = None,
    bundle_id: str | None = None,
    hardware_query: str | None = None,
    version: str | None = None,
    limit: int = 100,
    active_within_days: int | None = DEFAULT_ACTIVE_WITHIN_DAYS,
) -> dict[str, Any]:
    """Count (and optionally list) machines with software installed, filtered by hardware."""
    expanded = await expand_software_matchers(
        session,
        query=query,
        item_name=item_name,
        app_name=app_name,
        bundle_id=bundle_id,
    )
    if "error" in expanded:
        return expanded

    matchers = expanded["matchers"]
    if not matchers:
        return {"error": "Provide query, item_name, app_name, or bundle_id"}

    machine_query = apply_active_machine_filter(select(ClientMachine), active_within_days=active_within_days)
    result = await session.execute(machine_query)
    machines = result.scalars().all()

    matched: list[dict[str, Any]] = []
    for machine in machines:
        if not machine_matches_hardware(machine, hardware_query):
            continue
        installed_version = _find_installed_version(machine.installed_software, matchers)
        if installed_version is None:
            continue
        if version and compare_loose_versions(installed_version, version) != 0:
            continue

        hw = machine.hardware_info if isinstance(machine.hardware_info, dict) else {}
        matched.append(
            {
                "hostname": machine.hostname,
                "serial_number": machine.serial_number,
                "product_name": hw.get("product_name") or machine.machine_model,
                "machine_model": machine.machine_model,
                "installed_version": installed_version,
            }
        )

    rows = [
        [
            m["hostname"],
            m["serial_number"],
            m["product_name"],
            m["machine_model"],
            m["installed_version"],
        ]
        for m in matched[:limit]
    ]

    return {
        "matchers": matchers,
        "hardware_query": hardware_query,
        "version_filter": version,
        "active_within_days": active_within_days,
        "machines_in_scope": len(machines),
        "machine_count": len(matched),
        "returned": len(rows),
        "truncated": len(matched) > len(rows),
        "machines": matched[:limit],
        "table": {
            "columns": ["hostname", "serial_number", "product_name", "machine_model", "installed_version"],
            "rows": rows,
        },
    }
