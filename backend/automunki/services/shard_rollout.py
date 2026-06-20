"""Production shard rollout: separate from catalog promotion.

Writes ``installable_condition: shard <= N`` for pkginfo in production catalogs,
increasing daily until 100% of the fleet is eligible.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Literal

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from automunki.models.munki import (
    Catalog,
    ManifestItem,
    NetNewShardPolicy,
    PkgInfo,
    PkgInfoCatalog,
    ShardOverride,
    ShardRolloutStatus,
    WorkflowPreferences,
)
from automunki.services.audit import create_audit_entry

logger = structlog.get_logger()

DeploymentStatus = Literal[
    "not_in_production",
    "pending_rollout",
    "sharding",
    "fully_deployed",
    "paused",
]

_SHARD_CONDITION_RE = re.compile(r"^\s*shard\s*<=\s*(\d+)\s*$", re.IGNORECASE)


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def compute_shard_percent(
    shard_started_at: datetime,
    rollout_days: int,
    *,
    channel_multiplier: float = 1.0,
    now: datetime | None = None,
) -> int:
    """Return 0–100 percent of fleet eligible today (autopromote-compatible)."""
    if rollout_days <= 0:
        return 100
    mult = channel_multiplier if channel_multiplier > 0 else 1.0
    now_dt = _as_utc(now or datetime.now(UTC))
    started = _as_utc(shard_started_at)
    current_day = (now_dt.date() - started.date()).days + 1
    daily_pct = 100.0 / (rollout_days * mult)
    total_shard = int(daily_pct * current_day)
    return min(100, max(0, total_shard))


def installable_condition_for_percent(percent: int) -> str | None:
    if percent >= 100:
        return None
    return f"shard <= {percent}"


def parse_shard_percent_from_condition(condition: str | None) -> int | None:
    if not condition:
        return None
    m = _SHARD_CONDITION_RE.match(condition.strip())
    if not m:
        return None
    return int(m.group(1))


def derive_deployment_status(
    *,
    in_production: bool,
    shard_rollout_status: ShardRolloutStatus,
    shard_percent: int | None,
) -> DeploymentStatus:
    if not in_production:
        return "not_in_production"
    if shard_rollout_status == ShardRolloutStatus.paused:
        return "paused"
    if shard_rollout_status == ShardRolloutStatus.pending_approval:
        return "pending_rollout"
    if shard_rollout_status == ShardRolloutStatus.active:
        pct = shard_percent if shard_percent is not None else 0
        if pct < 100:
            return "sharding"
        return "fully_deployed"
    if shard_rollout_status in (
        ShardRolloutStatus.complete,
        ShardRolloutStatus.skipped,
        ShardRolloutStatus.none,
    ):
        return "fully_deployed"
    return "fully_deployed"


async def get_workflow_preferences(session: AsyncSession) -> WorkflowPreferences:
    wp = await session.get(WorkflowPreferences, 1)
    if not wp:
        raise RuntimeError("Workflow preferences not initialized")
    return wp


def pkg_in_production(pkg: PkgInfo) -> bool:
    return any(c.is_production for c in (pkg.catalogs or []))


async def production_catalog_entered_at(session: AsyncSession, pkg_id: uuid.UUID) -> datetime | None:
    row = (
        await session.execute(
            select(PkgInfoCatalog.entered_at)
            .join(Catalog, PkgInfoCatalog.catalog_id == Catalog.id)
            .where(
                PkgInfoCatalog.pkg_info_id == pkg_id,
                Catalog.is_production.is_(True),
            )
            .order_by(PkgInfoCatalog.entered_at.desc())
        )
    ).first()
    return row[0] if row else None


async def is_first_production_deploy(session: AsyncSession, pkg: PkgInfo) -> bool:
    """True when no *other* version of this name is currently in a production catalog."""
    result = await session.execute(
        select(PkgInfo.id)
        .join(PkgInfoCatalog, PkgInfo.id == PkgInfoCatalog.pkg_info_id)
        .join(Catalog, PkgInfoCatalog.catalog_id == Catalog.id)
        .where(
            PkgInfo.name == pkg.name,
            PkgInfo.id != pkg.id,
            PkgInfo.is_deleted.is_(False),
            Catalog.is_production.is_(True),
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is None


async def fetch_manifest_names_for_items(session: AsyncSession, names: set[str]) -> set[str]:
    if not names:
        return set()
    result = await session.execute(select(ManifestItem.item_name).where(ManifestItem.item_name.in_(names)))
    return {row[0] for row in result.all()}


async def fetch_manifests_referencing_name(session: AsyncSession, name: str) -> list[str]:
    from automunki.models.munki import Manifest

    result = await session.execute(
        select(Manifest.name)
        .join(ManifestItem, ManifestItem.manifest_id == Manifest.id)
        .where(ManifestItem.item_name == name)
        .distinct()
        .order_by(Manifest.name)
    )
    return [row[0] for row in result.all()]


async def names_with_other_production_versions(
    session: AsyncSession,
    pkg_ids: list[uuid.UUID],
    names: list[str],
) -> set[str]:
    """Names that have another version currently in production (not net-new)."""
    if not names:
        return set()
    result = await session.execute(
        select(PkgInfo.name)
        .join(PkgInfoCatalog, PkgInfo.id == PkgInfoCatalog.pkg_info_id)
        .join(Catalog, PkgInfoCatalog.catalog_id == Catalog.id)
        .where(
            PkgInfo.name.in_(names),
            PkgInfo.id.notin_(pkg_ids),
            PkgInfo.is_deleted.is_(False),
            Catalog.is_production.is_(True),
        )
        .distinct()
    )
    return {row[0] for row in result.all()}


def _apply_shard_fields(
    pkg: PkgInfo,
    *,
    status: ShardRolloutStatus,
    shard_started_at: datetime | None,
    shard_percent: int | None,
    installable_condition: str | None,
) -> None:
    pkg.shard_rollout_status = status
    pkg.shard_started_at = shard_started_at
    pkg.shard_percent = shard_percent
    pkg.installable_condition = installable_condition


async def init_shard_rollout(
    session: AsyncSession,
    pkg: PkgInfo,
    *,
    user_email: str = "system:shard-rollout",
) -> None:
    """Initialize or reset shard state when production catalog membership changes."""
    if not pkg_in_production(pkg):
        if pkg.shard_rollout_status != ShardRolloutStatus.paused:
            _apply_shard_fields(
                pkg,
                status=ShardRolloutStatus.none,
                shard_started_at=None,
                shard_percent=None,
                installable_condition=None,
            )
            pkg.shard_override = None
        return

    wp = await get_workflow_preferences(session)
    if not wp.production_shard_enabled:
        _apply_shard_fields(
            pkg,
            status=ShardRolloutStatus.skipped,
            shard_started_at=None,
            shard_percent=100,
            installable_condition=None,
        )
        pkg.shard_override = None
        return

    if pkg.shard_override == ShardOverride.force_complete:
        return

    entered_at = await production_catalog_entered_at(session, pkg.id)
    net_new = await is_first_production_deploy(session, pkg)
    policy = wp.net_new_shard_policy

    if net_new and policy == NetNewShardPolicy.skip_until_approved:
        _apply_shard_fields(
            pkg,
            status=ShardRolloutStatus.pending_approval,
            shard_started_at=None,
            shard_percent=None,
            installable_condition=None,
        )
        return

    if net_new and policy == NetNewShardPolicy.immediate_full:
        _apply_shard_fields(
            pkg,
            status=ShardRolloutStatus.complete,
            shard_started_at=entered_at or datetime.now(UTC),
            shard_percent=100,
            installable_condition=None,
        )
        pkg.shard_override = None
        return

    started = entered_at or datetime.now(UTC)
    percent = compute_shard_percent(started, wp.production_shard_days)
    condition = installable_condition_for_percent(percent)
    status = ShardRolloutStatus.complete if percent >= 100 else ShardRolloutStatus.active
    _apply_shard_fields(
        pkg,
        status=status,
        shard_started_at=started,
        shard_percent=percent,
        installable_condition=condition,
    )
    if status == ShardRolloutStatus.complete:
        pkg.shard_override = None

    logger.info(
        "shard_rollout_initialized",
        pkg_name=pkg.name,
        version=pkg.version,
        net_new=net_new,
        status=status.value,
        shard_percent=percent,
    )


async def maybe_init_shard_after_catalog_change(
    session: AsyncSession,
    pkg_id: uuid.UUID,
    *,
    user_email: str = "system:shard-rollout",
) -> None:
    result = await session.execute(select(PkgInfo).options(selectinload(PkgInfo.catalogs)).where(PkgInfo.id == pkg_id))
    pkg = result.scalar_one_or_none()
    if not pkg or pkg.is_deleted:
        return
    await init_shard_rollout(session, pkg, user_email=user_email)


async def start_shard_rollout(
    session: AsyncSession,
    pkg: PkgInfo,
    *,
    user_id: uuid.UUID | None = None,
    user_email: str | None = None,
) -> None:
    if not pkg_in_production(pkg):
        raise ValueError("Package is not in a production catalog")
    wp = await get_workflow_preferences(session)
    now = datetime.now(UTC)
    percent = compute_shard_percent(now, wp.production_shard_days)
    condition = installable_condition_for_percent(percent)
    status = ShardRolloutStatus.complete if percent >= 100 else ShardRolloutStatus.active
    before = pkg.installable_condition
    _apply_shard_fields(
        pkg,
        status=status,
        shard_started_at=now,
        shard_percent=percent,
        installable_condition=condition,
    )
    pkg.shard_override = None
    await create_audit_entry(
        session,
        action="shard_start",
        entity_type="pkg_info",
        entity_id=str(pkg.id),
        entity_name=f"{pkg.name} {pkg.version}",
        user_id=user_id,
        user_email=user_email,
        before_snapshot={"installable_condition": before, "shard_rollout_status": "pending_approval"},
        after_snapshot={
            "installable_condition": condition,
            "shard_rollout_status": status.value,
            "shard_percent": percent,
        },
    )


async def pause_shard_rollout(
    session: AsyncSession,
    pkg: PkgInfo,
    *,
    user_id: uuid.UUID | None = None,
    user_email: str | None = None,
) -> None:
    before_status = pkg.shard_rollout_status.value
    pkg.shard_rollout_status = ShardRolloutStatus.paused
    pkg.shard_override = ShardOverride.pause
    await create_audit_entry(
        session,
        action="shard_pause",
        entity_type="pkg_info",
        entity_id=str(pkg.id),
        entity_name=f"{pkg.name} {pkg.version}",
        user_id=user_id,
        user_email=user_email,
        before_snapshot={"shard_rollout_status": before_status},
        after_snapshot={"shard_rollout_status": "paused"},
    )


async def complete_shard_rollout(
    session: AsyncSession,
    pkg: PkgInfo,
    *,
    user_id: uuid.UUID | None = None,
    user_email: str | None = None,
) -> None:
    before = pkg.installable_condition
    _apply_shard_fields(
        pkg,
        status=ShardRolloutStatus.complete,
        shard_started_at=pkg.shard_started_at or datetime.now(UTC),
        shard_percent=100,
        installable_condition=None,
    )
    pkg.shard_override = ShardOverride.force_complete
    await create_audit_entry(
        session,
        action="shard_complete",
        entity_type="pkg_info",
        entity_id=str(pkg.id),
        entity_name=f"{pkg.name} {pkg.version}",
        user_id=user_id,
        user_email=user_email,
        before_snapshot={"installable_condition": before},
        after_snapshot={"installable_condition": None, "shard_rollout_status": "complete"},
    )


async def _tick_one_pkg(session: AsyncSession, pkg: PkgInfo, wp: WorkflowPreferences, now: datetime) -> bool:
    if pkg.shard_override in (ShardOverride.pause, ShardOverride.force_complete):
        return False
    if pkg.shard_rollout_status != ShardRolloutStatus.active:
        return False
    if not pkg.shard_started_at:
        return False
    if not pkg_in_production(pkg):
        return False

    percent = compute_shard_percent(pkg.shard_started_at, wp.production_shard_days, now=now)
    condition = installable_condition_for_percent(percent)
    changed = pkg.shard_percent != percent or pkg.installable_condition != condition
    pkg.shard_percent = percent
    pkg.installable_condition = condition
    if percent >= 100:
        pkg.shard_rollout_status = ShardRolloutStatus.complete
        pkg.shard_override = None
    return changed


async def run_production_shard_tick(session: AsyncSession) -> list[dict]:
    wp = await get_workflow_preferences(session)
    if not wp.production_shard_enabled:
        return []

    now = datetime.now(UTC)
    result = await session.execute(
        select(PkgInfo)
        .options(selectinload(PkgInfo.catalogs))
        .where(
            PkgInfo.is_deleted.is_(False),
            PkgInfo.shard_rollout_status == ShardRolloutStatus.active,
        )
    )
    updated: list[dict] = []
    for pkg in result.scalars().all():
        if await _tick_one_pkg(session, pkg, wp, now):
            updated.append(
                {
                    "name": pkg.name,
                    "version": pkg.version,
                    "shard_percent": pkg.shard_percent,
                    "installable_condition": pkg.installable_condition,
                }
            )
    return updated


async def build_shard_status(session: AsyncSession, pkg: PkgInfo) -> dict:
    wp = await get_workflow_preferences(session)
    in_prod = pkg_in_production(pkg)
    net_new = await is_first_production_deploy(session, pkg) if in_prod else False
    manifest_names = await fetch_manifests_referencing_name(session, pkg.name)
    in_manifest = bool(manifest_names)
    deployment_status = derive_deployment_status(
        in_production=in_prod,
        shard_rollout_status=pkg.shard_rollout_status,
        shard_percent=pkg.shard_percent,
    )
    rollout_days = wp.production_shard_days
    current_day: int | None = None
    if pkg.shard_started_at and in_prod:
        now = datetime.now(UTC)
        current_day = (_as_utc(now).date() - _as_utc(pkg.shard_started_at).date()).days + 1

    manifest_warning = in_manifest and net_new and deployment_status in ("pending_rollout", "sharding")

    summary_parts: list[str] = []
    if not in_prod:
        summary_parts.append("Not in a production catalog.")
    elif deployment_status == "pending_rollout":
        summary_parts.append("Awaiting operator approval to start production shard rollout.")
    elif deployment_status == "sharding":
        pct = pkg.shard_percent or 0
        summary_parts.append(f"Sharding to production: {pct}% of fleet eligible (day {current_day} of {rollout_days}).")
    elif deployment_status == "paused":
        summary_parts.append("Shard rollout is paused; installable condition will not be updated automatically.")
    else:
        summary_parts.append("Fully deployed to production (no shard condition).")

    if manifest_warning:
        summary_parts.append(
            "Warning: this net-new title is referenced in manifests but not fully deployed — "
            "high-shard devices may report missing catalog items."
        )

    return {
        "active": in_prod
        and pkg.shard_rollout_status
        in (
            ShardRolloutStatus.pending_approval,
            ShardRolloutStatus.active,
            ShardRolloutStatus.paused,
        ),
        "summary": " ".join(summary_parts),
        "deployment_status": deployment_status,
        "shard_rollout_status": pkg.shard_rollout_status.value,
        "shard_percent": pkg.shard_percent,
        "shard_started_at": pkg.shard_started_at,
        "rollout_days": rollout_days,
        "current_day": current_day,
        "is_first_production_deploy": net_new,
        "in_manifest": in_manifest,
        "manifest_names": manifest_names,
        "manifest_warning": manifest_warning,
        "installable_condition": pkg.installable_condition,
        "production_shard_enabled": wp.production_shard_enabled,
        "net_new_shard_policy": wp.net_new_shard_policy.value,
    }


async def list_shard_queue_items(session: AsyncSession, *, limit: int = 30) -> list[dict]:
    result = await session.execute(
        select(PkgInfo)
        .options(selectinload(PkgInfo.catalogs))
        .where(
            PkgInfo.is_deleted.is_(False),
            PkgInfo.shard_rollout_status.in_(
                [
                    ShardRolloutStatus.pending_approval,
                    ShardRolloutStatus.active,
                    ShardRolloutStatus.paused,
                ]
            ),
        )
    )
    candidates = list(result.scalars().all())
    in_prod = [p for p in candidates if pkg_in_production(p)]
    if not in_prod:
        return []

    names = {p.name for p in in_prod}
    manifest_names = await fetch_manifest_names_for_items(session, names)

    out: list[dict] = []
    for pkg in in_prod:
        net_new = await is_first_production_deploy(session, pkg)
        deployment_status = derive_deployment_status(
            in_production=True,
            shard_rollout_status=pkg.shard_rollout_status,
            shard_percent=pkg.shard_percent,
        )
        out.append(
            {
                "id": pkg.id,
                "name": pkg.name,
                "version": pkg.version,
                "display_name": pkg.display_name,
                "deployment_status": deployment_status,
                "shard_rollout_status": pkg.shard_rollout_status.value,
                "shard_percent": pkg.shard_percent,
                "is_first_production_deploy": net_new,
                "in_manifest": pkg.name in manifest_names,
            }
        )

    def _sort_key(d: dict) -> tuple:
        status_order = {
            "pending_rollout": 0,
            "sharding": 1,
            "paused": 2,
        }
        return (
            status_order.get(d.get("deployment_status"), 9),
            d.get("name") or "",
            d.get("version") or "",
        )

    out.sort(key=_sort_key)
    return out[: max(0, min(limit, 200))]


def deployment_fields_for_summary(
    pkg: PkgInfo,
    *,
    in_manifest: bool,
    is_first_production_deploy: bool,
) -> dict:
    in_prod = pkg_in_production(pkg)
    deployment_status = derive_deployment_status(
        in_production=in_prod,
        shard_rollout_status=pkg.shard_rollout_status,
        shard_percent=pkg.shard_percent,
    )
    return {
        "deployment_status": deployment_status,
        "shard_percent": pkg.shard_percent if in_prod else None,
        "is_first_production_deploy": is_first_production_deploy if in_prod else False,
        "in_manifest": in_manifest,
    }
