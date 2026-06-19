"""Safe, parameterized query handlers for the insights tool registry."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from automunki.models.client import ClientMachine
from automunki.models.munki import PkgInfo
from automunki.services.insights.machine_activity import DEFAULT_ACTIVE_WITHIN_DAYS, apply_active_machine_filter
from automunki.services.insights.software_resolve import (
    expand_software_matchers,
    resolve_software_identity,
    software_entry_matches,
)
from automunki.services.promotion import list_channel_promotion_queue_items


def _version_sort_key(version: str) -> tuple:
    parts: list[tuple[int, int | str]] = []
    for segment in version.replace("-", ".").split("."):
        try:
            parts.append((0, int(segment)))
        except ValueError:
            parts.append((1, segment))
    return tuple(parts)


def _find_installed_version(installed_software: object, matchers: list[str]) -> str | None:
    if not isinstance(installed_software, list):
        return None
    for entry in installed_software:
        if isinstance(entry, dict) and software_entry_matches(entry, matchers):
            version = entry.get("version")
            return str(version) if version else None
    return None


async def resolve_software_identity_handler(
    session: AsyncSession,
    *,
    query: str | None = None,
    item_name: str | None = None,
    app_name: str | None = None,
    bundle_id: str | None = None,
) -> dict[str, Any]:
    """Expose software resolution for the insights agent."""
    return await resolve_software_identity(
        session,
        query=query,
        item_name=item_name,
        app_name=app_name,
        bundle_id=bundle_id,
    )


async def get_fleet_compliance(session: AsyncSession) -> dict:
    """Fleet check-in compliance summary."""
    total = (await session.execute(select(func.count()).select_from(ClientMachine))).scalar() or 0

    recent_cutoff = datetime.now(UTC) - timedelta(days=7)
    recent = (
        await session.execute(
            select(func.count()).select_from(ClientMachine).where(ClientMachine.last_checkin_at >= recent_cutoff)
        )
    ).scalar() or 0

    stale_cutoff = datetime.now(UTC) - timedelta(days=30)
    stale = (
        await session.execute(
            select(func.count()).select_from(ClientMachine).where(ClientMachine.last_checkin_at < stale_cutoff)
        )
    ).scalar() or 0

    return {
        "total_machines": total,
        "checked_in_last_7_days": recent,
        "stale_over_30_days": stale,
        "compliance_percentage": round((recent / total * 100) if total > 0 else 0, 1),
    }


async def list_stale_machines(session: AsyncSession, *, days: int = 30, limit: int = 200) -> dict:
    """Machines whose last check-in is older than ``days`` (rolling window)."""
    cutoff = datetime.now(UTC) - timedelta(days=days)
    total = (
        await session.execute(
            select(func.count()).select_from(ClientMachine).where(ClientMachine.last_checkin_at < cutoff)
        )
    ).scalar() or 0

    result = await session.execute(
        select(ClientMachine)
        .where(ClientMachine.last_checkin_at < cutoff)
        .order_by(ClientMachine.last_checkin_at.asc().nullsfirst())
        .limit(limit)
    )
    machines = result.scalars().all()

    rows = [
        [
            m.hostname or "",
            m.serial_number,
            m.manifest_name or "",
            m.last_checkin_at.isoformat() if m.last_checkin_at else None,
        ]
        for m in machines
    ]

    return {
        "days": days,
        "total_stale": total,
        "returned": len(rows),
        "truncated": total > len(rows),
        "machines": [
            {
                "hostname": m.hostname,
                "serial_number": m.serial_number,
                "manifest_name": m.manifest_name,
                "last_checkin_at": m.last_checkin_at.isoformat() if m.last_checkin_at else None,
            }
            for m in machines
        ],
        "table": {
            "columns": ["hostname", "serial_number", "manifest_name", "last_checkin_at"],
            "rows": rows,
        },
    }


async def count_autopromote_enabled(session: AsyncSession) -> dict:
    """Count distinct software titles with auto-promote enabled on pkginfo."""
    count = (
        await session.execute(
            select(func.count(func.distinct(PkgInfo.name))).where(
                PkgInfo.auto_promote.is_(True),
                PkgInfo.is_deleted.is_(False),
            )
        )
    ).scalar() or 0

    names_result = await session.execute(
        select(func.distinct(PkgInfo.name))
        .where(PkgInfo.auto_promote.is_(True), PkgInfo.is_deleted.is_(False))
        .order_by(PkgInfo.name)
        .limit(100)
    )
    names = [row[0] for row in names_result.all()]

    return {
        "distinct_software_titles": count,
        "software_names": names,
        "names_truncated": count > len(names),
    }


async def list_autopromote_queue(session: AsyncSession, *, limit: int = 50) -> dict:
    """PkgInfo versions actively waiting in a promotion channel step."""
    items = await list_channel_promotion_queue_items(session, limit=limit)
    rows = [
        [
            item.get("name"),
            item.get("version"),
            item.get("channel_name"),
            item.get("next_source_catalog"),
            item.get("next_target_catalog"),
            item.get("leg_status"),
        ]
        for item in items
    ]
    return {
        "queue_count": len(items),
        "items": items,
        "table": {
            "columns": [
                "name",
                "version",
                "channel_name",
                "next_source_catalog",
                "next_target_catalog",
                "leg_status",
            ],
            "rows": rows,
        },
    }


async def _resolve_catalog_item_name(session: AsyncSession, hint: str) -> str:
    expanded = await expand_software_matchers(session, query=hint)
    canonical = expanded.get("canonical_item_name")
    if isinstance(canonical, str) and canonical.strip():
        return canonical.strip()
    return hint.strip()


async def get_installed_software_version_distribution(
    session: AsyncSession,
    *,
    query: str | None = None,
    item_name: str | None = None,
    app_name: str | None = None,
    bundle_id: str | None = None,
    active_within_days: int | None = DEFAULT_ACTIVE_WITHIN_DAYS,
) -> dict:
    """Version histogram from fleet application inventory snapshots."""
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

    machine_query = apply_active_machine_filter(
        select(ClientMachine).where(ClientMachine.installed_software.isnot(None)),
        active_within_days=active_within_days,
    )
    result = await session.execute(machine_query)
    machines = result.scalars().all()

    version_counts: dict[str, int] = {}
    machines_with_app = 0
    for machine in machines:
        version = _find_installed_version(machine.installed_software, matchers)
        if version is None:
            continue
        machines_with_app += 1
        version_counts[version] = version_counts.get(version, 0) + 1

    distribution = [
        {"version": version, "machine_count": count}
        for version, count in sorted(version_counts.items(), key=lambda x: (-x[1], _version_sort_key(x[0])))
    ]

    rows = [[d["version"], d["machine_count"]] for d in distribution]

    return {
        "matchers": matchers,
        "resolution": expanded.get("resolution"),
        "active_within_days": active_within_days,
        "machines_in_scope": len(machines),
        "machines_with_app": machines_with_app,
        "version_distribution": distribution,
        "table": {
            "columns": ["version", "machine_count"],
            "rows": rows,
        },
    }


async def get_catalog_latest_version(
    session: AsyncSession,
    *,
    item_name: str | None = None,
    query: str | None = None,
) -> dict:
    """Latest non-deleted pkginfo version for a Munki item name."""
    hint = (query or item_name or "").strip()
    if not hint:
        return {"error": "Provide item_name or query"}

    name = await _resolve_catalog_item_name(session, hint)
    result = await session.execute(
        select(PkgInfo.version, PkgInfo.display_name).where(
            PkgInfo.name == name,
            PkgInfo.is_deleted.is_(False),
        )
    )
    rows = result.all()
    if not rows:
        # Fuzzy fallback: first pkginfo match from resolution
        resolved = await resolve_software_identity(session, query=hint, item_name=item_name)
        for match in resolved.get("pkginfo_matches") or []:
            alt = match.get("item_name")
            if not alt:
                continue
            result = await session.execute(
                select(PkgInfo.version, PkgInfo.display_name).where(
                    PkgInfo.name == alt,
                    PkgInfo.is_deleted.is_(False),
                )
            )
            rows = result.all()
            if rows:
                name = alt
                break

    versions = [row[0] for row in rows]
    display_name = rows[0][1] if rows else None
    if not versions:
        return {"item_name": name, "query": hint, "latest_version": None, "version_count": 0}

    latest = max(versions, key=_version_sort_key)
    return {
        "item_name": name,
        "display_name": display_name,
        "query": hint,
        "latest_version": latest,
        "version_count": len(versions),
        "all_versions": sorted(versions, key=_version_sort_key, reverse=True)[:20],
    }


async def compare_fleet_version_to_latest(
    session: AsyncSession,
    *,
    query: str | None = None,
    item_name: str | None = None,
    app_name: str | None = None,
    bundle_id: str | None = None,
    active_within_days: int | None = DEFAULT_ACTIVE_WITHIN_DAYS,
) -> dict:
    """Percentage of inventoried machines on the latest catalog version."""
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

    catalog_hint = expanded.get("canonical_item_name") or query or item_name or app_name or bundle_id or ""
    catalog = await get_catalog_latest_version(session, query=str(catalog_hint))
    latest = catalog.get("latest_version")
    if not latest:
        return {
            "matchers": matchers,
            "resolution": expanded.get("resolution"),
            "latest_catalog_version": None,
            "error": f"No pkginfo found for {catalog_hint!r}",
        }

    distribution = await get_installed_software_version_distribution(
        session,
        query=query,
        item_name=item_name,
        app_name=app_name,
        bundle_id=bundle_id,
        active_within_days=active_within_days,
    )
    total_with_app = distribution["machines_with_app"]
    on_latest = 0
    for entry in distribution["version_distribution"]:
        if entry["version"] == latest:
            on_latest = entry["machine_count"]
            break

    percentage = round((on_latest / total_with_app * 100) if total_with_app > 0 else 0, 1)

    return {
        "matchers": matchers,
        "resolution": expanded.get("resolution"),
        "active_within_days": active_within_days,
        "machines_in_scope": distribution.get("machines_in_scope"),
        "catalog_item_name": catalog.get("item_name"),
        "catalog_display_name": catalog.get("display_name"),
        "latest_catalog_version": latest,
        "machines_with_app": total_with_app,
        "machines_on_latest": on_latest,
        "percentage_on_latest": percentage,
        "version_distribution": distribution["version_distribution"],
        "table": distribution.get("table"),
    }
